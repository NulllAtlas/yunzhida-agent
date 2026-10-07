"""从用户补充文字里抽取现场要素（关键词规则，**不是检测结果**）。

为什么需要：视频/照片识别不出"信号灯归属"——同一路口多方向红绿灯并存时
`scene.traffic_light` 只能给出 `mixed`，也认不出路口指示牌；而这些恰是判责的关键要素。
用户自己往往说得清清楚楚（"我直行是绿灯，对方闯红灯左转"）。
这里把它抽成结构化字段（`TextFacts`），以「用户陈述」的身份进判定上下文，
最终结论仍由 LLM 统一辅助输出（见 `services/llm.py::_RULES_PROMPT`）。

两条纪律：
1. **不冒充检测结果**：抽取出来的都是用户陈述，与检测结果冲突时以检测为准；
2. **不做过度归因**：没写"我方/对方"的裸"红灯"不硬塞给某一方，只记进 `matched`；
   光凭"某方是红灯"也不断言闯红灯（对方可能正停在路口等灯），
   只有明写"闯红灯"或"我方绿灯 + 对方红灯"这种两侧灯色相反的陈述才算指认。
"""
from __future__ import annotations

import re

from app.schemas.models import TextFacts

# 信号灯（口语里"灯"字常有省略，这里只看带"灯"的显式说法）
_LIGHT_WORDS: tuple[tuple[str, str], ...] = (
    ("绿灯", "green"),
    ("红灯", "red"),
    ("黄灯", "yellow"),
)

# 归属词：长的写在前面，"对方"要先于"他车"之类的短词命中
_SELF_WORDS = ("我的车", "我方车辆", "我方", "我车", "本车", "自己", "我")
# 不收裸"他"：会把"其他车辆"误判成对方
_OTHER_WORDS = ("对方车辆", "对方车", "对方", "对面", "他的车", "他车", "另一辆车", "另一方")

# 否定词出现在关键词前面时不算数（"我没闯红灯" / "没有压实线"）
_NEGATIONS = ("没有", "没", "未", "不是", "不", "无")
_NEGATION_WINDOW = 4
_ACTOR_WINDOW = 6

# 闯红灯（含口语变体）
_RED_RUN_WORDS = ("闯红灯", "冲红灯", "抢红灯", "红灯亮时通过")
# 闯黄灯/抢黄灯**不构成闯红灯**（与判定规则表一致），只算过错关键词
_YELLOW_RUN_WORDS = ("闯黄灯", "抢黄灯")

# 路口指示牌 / 标志 / 标线
_SIGN_WORDS = (
    "禁止左转", "禁止右转", "禁止掉头", "禁止通行", "禁止停车", "禁止超车", "禁止鸣笛",
    "让行标志", "停车让行", "减速让行", "限速", "单行道", "单向行驶", "导流线",
    "人行横道", "斑马线", "导向箭头", "停止线", "实线", "虚线", "黄网格", "网格线",
    "施工", "警示牌", "指示牌", "信号灯", "红绿灯", "路口标志",
)

# 其他过错关键词
_VIOLATION_WORDS = (
    "压实线", "压线", "越线", "逆行", "超速", "未打转向灯", "没打转向灯", "未开转向灯",
    "未让行", "不让行", "加塞", "强行变道", "连续变道", "占用应急车道", "违停",
    "酒驾", "疲劳驾驶", "接打电话", "闯黄灯", "抢黄灯",
)

_CLAUSE_SPLIT = re.compile(r"[，。；、,;.!！?？\s]+")


def _negated(clause: str, idx: int) -> bool:
    """关键词前面一小段里出现否定词 → 这条陈述不算数。"""
    window = clause[max(0, idx - _NEGATION_WINDOW):idx]
    return any(n in window for n in _NEGATIONS)


def _actor_near(clause: str, idx: int) -> str:
    """关键词前面一小段里找归属：self / other / ""（没说清）。

    中文把主语放在谓语前面（"对方闯红灯"、"我方是绿灯"），所以取关键词前的窗口即可；
    取不到就交给调用方退回整句判断。
    """
    window = clause[max(0, idx - _ACTOR_WINDOW):idx]
    for word in _OTHER_WORDS:
        if word in window:
            return "other"
    for word in _SELF_WORDS:
        if word in window:
            return "self"
    return ""


def _actor_of(clause: str) -> str:
    for word in _OTHER_WORDS:
        if word in clause:
            return "other"
    for word in _SELF_WORDS:
        if word in clause:
            return "self"
    return ""


def _add_once(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def extract_text_facts(text: str | None, raw_limit: int = 200) -> TextFacts:
    """把用户补充文字抽成结构化现场要素；没提到任何要素时 matched 为空。"""
    source = (text or "").strip()
    facts = TextFacts(raw=source[:raw_limit])
    if not source:
        return facts

    matched: list[str] = []

    for clause in _CLAUSE_SPLIT.split(source):
        if not clause:
            continue
        clause_actor = _actor_of(clause)

        for word, color in _LIGHT_WORDS:
            idx = clause.find(word)
            if idx < 0 or _negated(clause, idx):
                continue
            matched.append(word)
            who = _actor_near(clause, idx) or clause_actor
            if who == "self":
                facts.my_light = color
            elif who == "other":
                facts.other_light = color
            # 没说清是谁的灯：不硬塞给某一方

        for word in _RED_RUN_WORDS:
            idx = clause.find(word)
            if idx < 0 or _negated(clause, idx):
                continue
            matched.append(word)
            facts.red_light_violation = "yes"
            who = _actor_near(clause, idx) or clause_actor
            if who:
                facts.red_light_by = who

        for word in _YELLOW_RUN_WORDS:
            idx = clause.find(word)
            if idx >= 0 and not _negated(clause, idx):
                matched.append(word)
                _add_once(facts.violations, word)

        for word in _SIGN_WORDS:
            if word in clause:
                _add_once(facts.signs, word)
                matched.append(word)

        for word in _VIOLATION_WORDS:
            idx = clause.find(word)
            if idx >= 0 and not _negated(clause, idx):
                _add_once(facts.violations, word)
                matched.append(word)

    # 两侧灯色都写清且互相冲突 → 等价于"一方闯了灯"的陈述
    if facts.red_light_violation == "unknown":
        if facts.my_light == "green" and facts.other_light == "red":
            facts.red_light_violation, facts.red_light_by = "yes", "other"
        elif facts.my_light == "red" and facts.other_light == "green":
            facts.red_light_violation, facts.red_light_by = "yes", "self"

    for word in matched:
        _add_once(facts.matched, word)
    return facts
