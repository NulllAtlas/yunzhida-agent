"""路口场景要素识别（大模型看关键帧）：信号灯归属方向、人行横道、标线、标志牌、路型。

为什么要有这一层：YOLO 能框出信号灯、HSV 投票能给出颜色，但**认不出哪一盏管哪一方**
—— 同一路口多方向灯并存时只能给出 `mixed`，而闯红灯判定要求"能确认肇事车辆对应的
那组信号灯"才可认定（见 `app/services/llm.py` 的闯红灯规则）。人行横道、停止线、
导向箭头、标志牌这些要素 YOLO 的类别里根本没有，却恰恰是判责的关键。

**能力自适应**（本模块的核心约定）：模型能看图就用它的结果；看不见图就把整块留空、
原样返回，链路退回原有模式（YOLO + HSV）。判定"不能看图"的四种征兆都按"认不出"处理：
调用抛异常（含账号未开通的 402）、返回内容为空、内容里找不出 JSON、解析出来全是
unknown。四种都不报错、不重试、不阻塞 —— 换模型/换网络都不会把研判链路拖死。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# 抽帧缩放宽度：再大对判读信号灯/标线没有增益，只是白烧 token
_FRAME_WIDTH = 1024
_JPEG_QUALITY = 85

_PROMPT = """你是交通事故视频分析助手，正在看一段行车记录仪视频的若干帧画面。
只回答画面中**确实可见**的内容；看不清、不确定一律填 "unknown"，绝不猜测、绝不编造。

- self_light: **正对镜头**（即我方行进方向）那组信号灯的颜色：red / green / yellow / unknown
- other_light: 画面中其他方向（横向路口）可见信号灯的颜色，看不见填 unknown
- crosswalk: 是否有人行横道（斑马线）：present / absent / unknown
- road_markings: 可见的路面标线，取值取自 ["停止线", "人行横道", "导向箭头", "黄色网格", "车道分界线"]
- signs: 可见的交通标志牌，取值取自 ["让行", "停车", "禁止通行", "限速", "注意行人"]
- road: 路口类型：intersection / t_junction / roundabout / straight / other / unknown
- visibility: 天气与光线：day / night / dusk / rain / fog / unknown
- note: 一句话说明你判断 self_light 的依据（例如"画面右上方横杆上那组灯，亮的是红色"）

只输出 JSON，字段固定，不要输出其它文字：
{"self_light": "", "other_light": "", "crosswalk": "", "road_markings": [],
 "signs": [], "road": "", "visibility": "", "note": ""}"""

_LIGHT_WORDS = (("红", "red"), ("绿", "green"), ("黄", "yellow"))
_ROAD_WORDS = (("十字", "intersection"), ("交叉路口", "intersection"),
               ("t字", "t_junction"), ("丁字", "t_junction"), ("环岛", "roundabout"),
               ("直道", "straight"), ("直线", "straight"))
_VISIBILITY_WORDS = (("白天", "day"), ("日间", "day"), ("夜间", "night"),
                     ("夜", "night"), ("黄昏", "dusk"), ("傍晚", "dusk"),
                     ("雨", "rain"), ("雾", "fog"))

_MARKING_CHOICES = ("停止线", "人行横道", "导向箭头", "黄色网格", "车道分界线")
_SIGN_CHOICES = ("让行", "停车", "禁止通行", "限速", "注意行人")

# 已确认"看不见图"的模型：模型不是多模态 / 账号没开通时，每段视频都白调一次要等
# 好几秒（实测 8.4s/次），记住结论，同一进程内不再重复踩坑。
# 只记**确定性**结论（返回空 / 401·402·403 未开通）；网络抖动、超时不算 ——
# 一次抖动不该把功能永久关掉。键是模型名：换了模型就重新试。
_BLIND_MODELS: set[str] = set()


def _sample_frames(media_path: str, count: int) -> list[str]:
    """均匀抽 count 帧，返回 base64 JPEG 列表（读不出的帧直接跳过）。"""
    import cv2

    if count <= 0:
        return []
    cap = cv2.VideoCapture(str(media_path))
    if not cap.isOpened():
        return []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return []
        images: list[str] = []
        # (i+1)/(count+1)：取中间那几帧，避开片头片尾的过场/黑屏
        for i in range(count):
            idx = int(total * (i + 1) / (count + 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(idx, total - 1)))
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            if w > _FRAME_WIDTH:
                frame = cv2.resize(frame, (_FRAME_WIDTH, int(h * _FRAME_WIDTH / w)))
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
            if ok:
                images.append(base64.b64encode(buf.tobytes()).decode())
        return images
    finally:
        cap.release()


def _parse_json(text: str) -> dict | None:
    """从模型回复里抠出 JSON 对象（容忍 ```json 围栏与前后废话）。"""
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
    return None


def _key_map(data: dict) -> dict[str, str]:
    """键名归一化：只留字母数字并小写（selfLight / self_light / self light 等价）。"""
    return {re.sub(r"[^a-z0-9]", "", str(k).lower()): k for k in data}


def _pick(data: dict, name: str) -> Any:
    """容错取字段。

    实测模型会把 self_light 写成 `selfshow_light` 这类错拼/变体，键名严格相等
    匹配会让整段结果作废 —— 先精确匹配，再退化成"键里包含名字的每一段"。
    """
    keys = _key_map(data)
    flat = re.sub(r"[^a-z0-9]", "", name.lower())
    if flat in keys:
        return data[keys[flat]]
    parts = [p for p in re.split(r"[^a-z0-9]+", name.lower()) if p]
    if parts:
        for k, original in keys.items():
            if all(p in k for p in parts):
                return data[original]
    return None


def _norm_light(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in ("red", "green", "yellow", "mixed"):
        return text
    for word, state in _LIGHT_WORDS:
        if word in text:
            return state
    return "unknown"


def _norm_crosswalk(value: Any) -> str:
    if isinstance(value, bool):
        return "present" if value else "absent"
    text = str(value or "").strip().lower()
    if text in ("present", "absent", "unknown"):
        return text
    if text in ("true", "yes", "1") or text.startswith("有"):
        return "present"
    if text in ("false", "no", "0") or text.startswith(("无", "没")):
        return "absent"
    return "unknown"


def _norm_choice(value: Any, words: tuple[tuple[str, str], ...],
                 allowed: tuple[str, ...]) -> str:
    text = str(value or "").strip().lower()
    if text in allowed:
        return text
    for word, mapped in words:
        if word in text:
            return mapped
    return "unknown"


def _norm_list(value: Any, allowed: tuple[str, ...]) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[、,，;；/]", value)
    elif isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    else:
        return []
    out: list[str] = []
    for item in items:
        item = item.strip()
        if not item or item.lower() in ("unknown", "none", "无"):
            continue
        for choice in allowed:
            if choice in item and choice not in out:
                out.append(choice)
                break
    return out


def normalize_vision(data: dict, *, model: str, frames: int) -> dict:
    """模型返回的 JSON → SceneVision 字段（不认识的一律 unknown，不猜）。"""
    note = _pick(data, "note")
    return {
        "model": model,
        "frames": frames,
        "self_light": _norm_light(_pick(data, "self_light")),
        "other_light": _norm_light(_pick(data, "other_light")),
        "crosswalk": _norm_crosswalk(_pick(data, "crosswalk")),
        "road_markings": _norm_list(_pick(data, "road_markings"), _MARKING_CHOICES),
        "signs": _norm_list(_pick(data, "signs"), _SIGN_CHOICES),
        "road": _norm_choice(_pick(data, "road"), _ROAD_WORDS,
                             ("intersection", "t_junction", "roundabout",
                              "straight", "other", "unknown")),
        "visibility": _norm_choice(_pick(data, "visibility"), _VISIBILITY_WORDS,
                                   ("day", "night", "dusk", "rain", "fog", "unknown")),
        "note": str(note or "").strip()[:200],
    }


def _has_any(info: dict) -> bool:
    """有没有任何一条可用信息。

    全 unknown 视为"模型看不见这张图"（标题卡片、非道路画面、文本模型都是这个结果），
    不上报 —— 免得给判定 prompt 塞一句"什么都认不出"的空话。
    """
    return bool(
        info.get("self_light") not in (None, "unknown")
        or info.get("other_light") not in (None, "unknown")
        or info.get("crosswalk") not in (None, "unknown")
        or info.get("road_markings") or info.get("signs")
        or info.get("road") not in (None, "unknown")
        or info.get("visibility") not in (None, "unknown")
    )


async def recognize_scene_elements(media_path: str) -> dict | None:
    """抽帧 → 大模型识别 → 归一化。看不见图或任何失败都返回 None。"""
    if not (settings.moma_base_url and settings.moma_api_key):
        return None
    if settings.video_llm_model in _BLIND_MODELS:
        return None  # 这个模型已确认看不见图，不再白花抽帧与网络时间

    frames = await asyncio.to_thread(
        _sample_frames, media_path, settings.vision_scene_frames
    )
    if not frames:
        logger.info("场景要素识别：抽不到帧，跳过（%s）", media_path)
        return None

    client = AsyncOpenAI(
        api_key=settings.moma_api_key,
        base_url=settings.moma_base_url,
        timeout=settings.vision_scene_timeout_s,
        max_retries=0,  # 失败即退回原有模式，不在这里重试拖时间
    )
    content: list[dict] = [{"type": "text", "text": _PROMPT}]
    content += [{"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in frames]
    try:
        resp = await client.chat.completions.create(
            model=settings.video_llm_model,
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            max_tokens=500,
        )
    except Exception as exc:  # noqa: BLE001 — 未开通/不支持看图/超时都算"认不出"
        status = getattr(exc, "status_code", None)
        if status in (401, 402, 403) or "subscription_required" in str(exc):
            # 账号没开通这个模型：确定性的结论，记下来别再试
            _BLIND_MODELS.add(settings.video_llm_model)
        logger.info("场景要素识别不可用（%s），本次退回原有模式：%s",
                    settings.video_llm_model, exc)
        return None

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        # 收了图却回空串 = 这个模型看不见图（实测文本模型就是这样），别再试
        _BLIND_MODELS.add(settings.video_llm_model)
        logger.info("模型 %s 看图返回空（不是视觉模型），后续视频跳过识别、直接用原有模式",
                    settings.video_llm_model)
        return None
    data = _parse_json(text)
    if data is None:
        logger.info("模型 %s 的返回解析不出 JSON，本次退回原有模式", settings.video_llm_model)
        return None

    info = normalize_vision(data, model=settings.video_llm_model, frames=len(frames))
    if not _has_any(info):
        logger.info("模型 %s 未能从这几帧里认出任何路口要素，本次退回原有模式",
                    settings.video_llm_model)
        return None
    logger.info("场景要素识别完成：self_light=%s crosswalk=%s road=%s（%d 帧）",
                info["self_light"], info["crosswalk"], info["road"], len(frames))
    return info


async def enrich_scene_with_vision(raw: dict, media_path: str) -> dict:
    """把大模型识别的路口要素并进 scene dict；认不出就原样返回。

    与检测结果的关系：**检测优先**。YOLO 已经给出的 `road`/`lane_markings`/
    `visibility` 不被覆盖，只补它给不出的（YOLO 对这些一律填 "unknown"）。
    信号灯不做合并 —— YOLO 的 `traffic_lights` 是逐灯位置+颜色，大模型给不了
    逐灯坐标；大模型独有的"面向镜头那组灯是什么颜色"放在 `vision.self_light`，
    由 `scene_summary` 单独表述，避免两套数据搅在一起分不清谁说的。
    """
    if not settings.vision_scene_enabled or settings.use_mock:
        return raw
    try:
        info = await recognize_scene_elements(media_path)
    except Exception:  # noqa: BLE001 — 增强能力，任何意外都不该拖垮研判
        logger.warning("场景要素识别异常，退回原有模式（YOLO+HSV）", exc_info=True)
        return raw
    if not info:
        return raw

    out = dict(raw)
    out["vision"] = info
    if str(out.get("road") or "unknown") in ("", "unknown") and info["road"] != "unknown":
        out["road"] = info["road"]
    if (str(out.get("lane_markings") or "unknown") in ("", "unknown")
            and info["road_markings"]):
        out["lane_markings"] = "、".join(info["road_markings"])
    if (str(out.get("visibility") or "unknown") in ("", "unknown")
            and info["visibility"] != "unknown"):
        out["visibility"] = info["visibility"]
    return out
