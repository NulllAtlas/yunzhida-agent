"""
LLM 网关服务（M3/M4）。

- use_mock=True  时返回确定性模板结果（保证全链路可跑，无凭据也能演示）
- use_mock=False 时调用真实 MoMA 网关（OpenAI 兼容），统一 `call_chat`，
  带鉴权 / 超时 / 重试；判定结果按 JSON 解析并容错降级回规则匹配。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# 应急方案润色预算：它只是把模板改得更好读，失败就原样返回模板，
# 不值得占用与判定同等的等待时间。
_REFINE_TIMEOUT_S = 20.0

# 责任判定 mock —— 基于关键要素做规则式判定，供 MVP 闭环演示 / LLM 解析失败兜底
_RULE_JUDGMENTS = [
    {
        "match": ["追尾", "追尾", "follow"],
        "accident_type": "追尾",
        "resp": {"party_1": "primary", "party_2": "none", "split": "100/0"},
        "basis": ["《道交法》第43条 同车道行驶后车应与前车保持安全距离"],
        "reasoning": ["后车未与前车保持足以采取紧急制动措施的安全距离", "前车无过错"],
    },
    {
        "match": ["变道", "变道", "lane"],
        "accident_type": "普通碰撞",
        "resp": {"party_1": "primary", "party_2": "none", "split": "100/0"},
        "basis": ["《实施条例》第44条 变更车道不得影响相关车道内正常行驶的机动车"],
        "reasoning": ["变道方未让行原车道正常行驶车辆"],
    },
    {
        "match": ["路口", "未让行", "intersection"],
        "accident_type": "普通碰撞",
        "resp": {"party_1": "primary", "party_2": "secondary", "split": "70/30"},
        "basis": ["《道交法》第47条 机动车行经路口应让行", "《实施条例》第51条 通过路口让行规定"],
        "reasoning": ["一方未按让行规则通行", "另一方未尽注意义务，承担次要责任"],
    },
]

_JUDGE_FALLBACK = {
    "accident_type": "unknown",
    "responsibility": {"party_1": "unknown", "party_2": "unknown", "split": ""},
    "basis": ["需补充现场要素"],
    "reasoning": ["要素不足，无法给出明确责任倾向"],
    "confidence": 0.3,
}

_ALLOWED_PARTY = ("primary", "secondary", "equal", "none", "unknown")

# 责任判定规则表（本版本聚焦三类事故），作为 LLM 判责的约束框架：
# LLM 只负责按证据归类与识别双方，比例与法条由规则表决定，保证同类事故结论稳定
_RULES_PROMPT = """\
判定规则表（类别 | 场景特征 | 责任倾向 | 法条）：
1. 追尾 | 同车道行驶后车碰撞前车（含静止/缓行前车）尾部 | 后车 100/0；前车突然倒车/溜车则责任转移 | 《道交法》第43条
2. 普通碰撞 | 两车或车与行人的其余碰撞（变道刮蹭、路口未让行、侧碰、转弯碰撞等） | 过错方主责/全责，另一方按过错承担次责或无责 | 《实施条例》第44条（变道）、《道交法》第47条（未让行）等
3. 单方撞击公共设施 | 仅一个移动车辆撞击护栏/树木/杆柱等固定物，无他方车辆或行人参与碰撞 | 驾驶方全责 100/0 | 《道交法》第22条

碰撞形态（场景描述里会给出，务必据此归类）：
- 形态"同向（追尾/同向刮碰）"：才可归为追尾；
- 形态"交叉（路口侧向碰撞）"：属路口交叉碰撞，必须归为普通碰撞并在 reasoning 说明，
  **不得**归为追尾——只看"一车动、一车停"会把交叉碰撞误归成追尾；
- 形态"无法判定"：按描述归类，但 reasoning 里要说明形态无法确认。

闯红灯判定（要素，非事故类型）：
- 只有能确认**肇事车辆所对应的那组信号灯**为红时，才可输出 red_light_violation=yes；
- 若场景描述指出"同时检出红灯与绿灯（不同方向并存）"，说明无法把车辆关联到具体信号灯，
  必须输出 unknown，并在 reasoning 里说明原因；
- 场景完全未识别出信号灯 → unknown；能确认为绿/黄且车辆正常通行 → no。
- **补充描述可以补上检测认不出的信号灯归属**：场景里会带一段"用户陈述"（例如
  "我方方向 绿灯、对方方向 红灯；指认对方闯红灯"）。当检测结果无法关联信号灯
  （`mixed` / 未能识别）而用户陈述明确指认了归属时，**可以采用用户陈述判红灯**，
  但必须在 reasoning 里注明"依据用户补充描述"，并在 confidence 上体现这层不确定性；
  用户陈述与检测结果冲突时**以检测为准**，同时说明冲突。
- "闯黄灯 / 抢黄灯"不构成闯红灯（仍按 unknown 处理，可在 reasoning 里说明）。
"""


def _fact_value(facts: Any, key: str, default: Any = None) -> Any:
    """兼容 TextFacts 对象与 dict 两种入参（测试里常直接传 dict）。"""
    if facts is None:
        return default
    if isinstance(facts, dict):
        return facts.get(key, default)
    return getattr(facts, key, default)


def _rule_red_light(facts: Any) -> str:
    """规则兜底里的闯红灯结论：只看用户陈述（检测侧没有可用信号灯归属时才兜底）。

    检测结果优先：这个函数只在 mock 模式或 LLM 输出不可解析时被调用。
    """
    if _fact_value(facts, "red_light_violation") == "yes":
        return "yes"
    if _fact_value(facts, "my_light") in ("green", "yellow"):
        # 用户明说自己是绿/黄灯正常通行 → 不构成闯红灯（与规则表一致）
        return "no"
    return "unknown"


def _rule_judge(scene_text: str, facts: Any = None) -> dict:
    """规则式兜底判定（mock 或 LLM 解析失败时使用）。"""
    red_light = _rule_red_light(facts)
    for rule in _RULE_JUDGMENTS:
        if any(k in scene_text for k in rule["match"]):
            return {
                "accident_type": rule["accident_type"],
                "responsibility": rule["resp"],
                "basis": rule["basis"],
                "reasoning": rule["reasoning"],
                "red_light_violation": red_light,
                "confidence": 0.8,
            }
    fallback = dict(_JUDGE_FALLBACK)
    fallback["red_light_violation"] = red_light
    return fallback


def _as_pairs(evidence: Any) -> list[tuple[str, str]]:
    """把检索结果规整成 (title, content) 列表。

    上游传入的是 RetrievedDoc(pydantic) 对象列表，早期实现按 dict 调用 .get()，
    会抛 AttributeError 并被静默吞掉，导致 prompt 里法条上下文恒为空。
    """
    pairs: list[tuple[str, str]] = []
    for item in evidence or []:
        if isinstance(item, dict):
            title = str(item.get("title", ""))
            content = str(item.get("content", ""))
        else:
            title = str(getattr(item, "title", ""))
            content = str(getattr(item, "content", ""))
        if title or content:
            pairs.append((title, content))
    return pairs


class LLMService:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """惰性构建 OpenAI 兼容客户端（指向 MoMA 网关）。"""
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=settings.moma_base_url or None,
                api_key=settings.moma_api_key or "not-set",
                timeout=settings.llm_timeout_s,
                max_retries=settings.llm_max_retries,
            )
        return self._client

    def reset_client(self) -> None:
        """丢弃缓存的网关客户端：运行时改了 url/key 后，下次调用用新凭据重建。"""
        self._client = None

    async def call_chat(self, messages: list[dict], model: str | None = None,
                        temperature: float = 0.2,
                        timeout_s: float | None = None) -> str:
        """调用 MoMA 网关，返回文本内容。

        use_mock 或未配置网关地址时走内置 mock：直接把最后一条 user 内容原样返回，
        保证不依赖网络也能演示。

        超时用 asyncio.wait_for 做**墙钟硬约束**：httpx 的 read timeout 只在
        "完全无数据流动"时才触发，网关只要断断续续吐字节就会不断重置计时器
        （实测一次请求挂了 24 分钟）。这里从外面兜一层，保证调用一定在
        timeout_s 内返回或抛出。
        """
        model = model or settings.model_strong or "default"
        if settings.use_mock or not settings.moma_base_url:
            for m in reversed(messages):
                if m.get("role") == "user":
                    return str(m["content"])
            return ""
        budget = settings.llm_timeout_s if timeout_s is None else timeout_s
        resp = await asyncio.wait_for(
            self._get_client().chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            ),
            timeout=budget,
        )
        return (resp.choices[0].message.content or "").strip()

    async def probe(self, base_url: str, api_key: str, model: str,
                    timeout_s: float = 20.0) -> dict:
        """用给定凭据做一次最小调用，验证 url / key / model 三者是否匹配。

        不修改全局配置——先在首页"测试连接"里验证通过，再决定是否应用，
        避免填错一个字段就把在跑的判定链路弄挂。
        """
        client = AsyncOpenAI(
            base_url=base_url or None,
            api_key=api_key or "not-set",
            timeout=timeout_s,
            max_retries=0,
        )
        started = time.monotonic()
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                ),
                timeout=timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 — 任何失败都如实回传给前端
            return {
                "ok": False,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "error": f"{type(exc).__name__}: {exc}"[:300],
            }
        return {
            "ok": True,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "reply_model": getattr(resp, "model", "") or model,
        }

    async def judge(self, scene_text: str, evidence: Any,
                    pre_validated: bool = False, facts: Any = None) -> dict:
        """责任判定：严格按规则表判责（LLM 归类 + 引用证据），解析失败回退规则匹配。

        pre_validated=True 表示事故真实性已由前置代码门控确认（视频来源），
        prompt 中不再要求 LLM 复判真实性，避免两层门控重复否决导致判定翻转。

        facts 是用户补充文字里抽出的现场要素（TextFacts）：它以「用户陈述」的形式
        出现在 scene_text 里供 LLM 采信，同时在规则兜底路径里决定闯红灯结论。
        """
        if settings.use_mock:
            return _rule_judge(scene_text, facts)

        laws = "\n".join(f"- {title}: {content}" for title, content in _as_pairs(evidence))
        gate_line = (
            "事故真实性已由视频感知系统前置确认（含高速移动目标与高置信碰撞事件），"
            "请直接按规则表归类，不要输出'非事故'。\n" if pre_validated else ""
        )
        gate_req = (
            "" if pre_validated else (
                "0. 先判断这是否为一起真实的交通事故：若事故描述与证据不像真实碰撞"
                "（所有目标速度很低、无高速接近或速度骤变、像日常通行/正常车流），"
                "则判定为误报——输出 accident_type 填'非事故'，responsibility 全部 unknown，"
                "split 填空，reasoning 说明'未检测到明显事故特征，疑似误报'；\n"
            )
        )
        prompt = (
            "你是一名专业的交通事故责任研判辅助助手。请严格按下面的判定规则表判责。\n\n"
            f"{gate_line}{_RULES_PROMPT}\n"
            "要求：\n"
            f"{gate_req}"
            "1. 根据事故描述把真实事故归类到规则表中的三类之一（accident_type 用该类名称；"
            "无法归类时填 unknown）；\n"
            "2. parties 必须分别说明事故双方：role 填当事方角色（后车/前车/驾驶方/行人等），"
            "type 填检测到的目标类型（car/truck/pedestrian 等）；单方事故只给一个元素；\n"
            "3. red_light_violation 按闯红灯判定规则输出 yes/no/unknown；\n"
            "4. responsibility/basis 严格采用该类规则的责任倾向与法条，不要自行变更比例；\n"
            "5. reasoning 结合事故描述与可引用法规/案例佐证归类；\n"
            "6. 仅当事故描述完全为空时才输出 unknown（split 填空、basis 填['需补充现场要素']）；"
            "描述简短时也必须按关键词归类给出结论。\n"
            "只输出 JSON，不要输出其它文字。JSON 结构：\n"
            '{"accident_type": "追尾|普通碰撞|单方撞击公共设施|非事故|unknown", '
            '"parties": [{"role": "后车", "type": "car"}, {"role": "前车", "type": "truck"}], '
            '"red_light_violation": "yes|no|unknown", '
            '"responsibility": {"party_1": "primary|secondary|equal|none|unknown", '
            '"party_2": "primary|secondary|equal|none|unknown", "split": "70/30"}, '
            '"basis": ["法条依据"], "reasoning": ["判定理由分条"], '
            '"confidence": 0.0到1.0之间的数字}\n\n'
            f"事故描述：{scene_text}\n\n可引用法规/案例：\n{laws}"
        )
        try:
            raw = await self.call_chat([{"role": "user", "content": prompt}], temperature=0)
        except Exception:  # noqa: BLE001  — 网络/超时/鉴权失败
            logger.warning("judge LLM 调用失败，回退规则匹配", exc_info=True)
            return _rule_judge(scene_text, facts)

        parsed = self._parse_judgment(raw)
        if parsed is None:
            # 原先是 `... or _rule_judge(...)` 的静默回退，出了问题在日志里
            # 完全看不出来（实测一次 LLM 返回无法解析，排查时毫无线索）。
            logger.warning("judge LLM 输出无法解析，回退规则匹配；原文前 300 字: %s",
                           (raw or "")[:300])
            return _rule_judge(scene_text, facts)
        return parsed

    def _parse_judgment(self, text: str) -> dict | None:
        """从 LLM 输出中稳健提取 JSON，字段缺失时回退 None。"""
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        resp = data.get("responsibility") or {}
        party_1 = resp.get("party_1") or "unknown"
        party_2 = resp.get("party_2") or "unknown"
        if party_1 not in _ALLOWED_PARTY:
            party_1 = "unknown"
        if party_2 not in _ALLOWED_PARTY:
            party_2 = "unknown"
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        split = str(resp.get("split") or "")
        # split 只接受 "数字/数字" 格式，LLM 输出其它值时置空
        if not re.fullmatch(r"\d{1,3}/\d{1,3}", split):
            split = ""
        parties = data.get("parties")
        parties_out = (
            [{"role": str(p.get("role", "")), "type": str(p.get("type", ""))}
             for p in parties if isinstance(p, dict)]
            if isinstance(parties, list) else []
        )
        rlv = str(data.get("red_light_violation") or "unknown")
        if rlv not in ("yes", "no", "unknown"):
            rlv = "unknown"
        return {
            "accident_type": str(data.get("accident_type") or ""),
            "parties": parties_out,
            "red_light_violation": rlv,
            "responsibility": {"party_1": party_1, "party_2": party_2, "split": split},
            "basis": [str(b) for b in (data.get("basis") or [])],
            "reasoning": [str(r) for r in (data.get("reasoning") or [])],
            "confidence": confidence,
        }

    async def draft_response(self, accident_type: str) -> dict:
        """应急方案模板（规则基）。MVP 阶段直接返回模板，迭代接 LLM 润色。"""
        templates = {
            "vehicle_pedestrian": {
                "priority": 1,
                "steps": [
                    {"order": 1, "action": "立即开启双闪，停车熄火", "urgent": True},
                    {"order": 2, "action": "拨打 120 急救，说明伤员情况", "urgent": True},
                    {"order": 3, "action": "拨打 122/110 报警", "urgent": True},
                    {"order": 4, "action": "放置三角警示牌（来车方向 50 米）", "urgent": True},
                    {"order": 5, "action": "保护现场，勿移动伤员，等待救援", "urgent": True},
                ],
                "insurance": "同步拨打保险公司报案，拍摄现场照片与全景视频，保留证据。",
            },
            "rear_end": {
                "priority": 2,
                "steps": [
                    {"order": 1, "action": "开启双闪，停车熄火", "urgent": True},
                    {"order": 2, "action": "放置三角警示牌（来车方向 50 米）", "urgent": True},
                    {"order": 3, "action": "人员撤至安全地带，勿留在车道", "urgent": True},
                    {"order": 4, "action": "无伤亡可先拍照固定证据后撤离至安全处协商", "urgent": False},
                ],
                "insurance": "拨打保险报案，保留现场照片与行车记录仪。",
            },
        }
        return templates.get(
            accident_type,
            {
                "priority": 2,
                "steps": [
                    {"order": 1, "action": "开启双闪，停车熄火", "urgent": True},
                    {"order": 2, "action": "放置三角警示牌", "urgent": True},
                    {"order": 3, "action": "人员撤至安全地带", "urgent": True},
                    {"order": 4, "action": "有伤亡拨打 120，报警 122/110", "urgent": True},
                ],
                "insurance": "保留现场证据，及时报保险。",
            },
        )

    async def refine_response(self, accident_type: str, scene_text: str, template: dict) -> dict:
        """用 LLM 润色应急模板（仅在 use_mock=False 且配置网关时生效）。

        任何失败（网络/解析/字段异常）都原样返回模板，保证应急步骤永不缺失。
        """
        if settings.use_mock or not settings.moma_base_url:
            return template
        actions = [s["action"] for s in template.get("steps", [])]
        prompt = (
            "你是交通事故应急处置助手。请把下面针对事故类型 "
            f"{accident_type} 的处置步骤，结合现场描述润色为更清晰、可执行的短句，"
            "保持条数与顺序不变。只输出 JSON："
            '{"steps": ["步骤1", "步骤2", ...], "insurance": "保险指引一句话"}\n\n'
            f"现场描述：{scene_text}\n原始步骤：{json.dumps(actions, ensure_ascii=False)}"
        )
        try:
            raw = await self.call_chat(
                [{"role": "user", "content": prompt}],
                timeout_s=min(_REFINE_TIMEOUT_S, settings.llm_timeout_s),
            )
            data = self._parse_json_block(raw)
            steps = data.get("steps") if isinstance(data, dict) else None
            if not isinstance(steps, list) or len(steps) != len(template.get("steps", [])):
                return template
            refined = json.loads(json.dumps(template))  # 深拷贝，避免污染模板
            for idx, text in enumerate(steps):
                refined["steps"][idx]["action"] = str(text)
            if data.get("insurance"):
                refined["insurance"] = str(data["insurance"])
            return refined
        except Exception:  # noqa: BLE001
            logger.warning("应急步骤润色失败，原样返回模板", exc_info=True)
            return template

    @staticmethod
    def _parse_json_block(text: str) -> Any:
        """从可能带 markdown 包裹的文本中提取第一个 JSON 对象/数组。"""
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


llm_service = LLMService()