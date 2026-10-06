"""补充文字里的现场要素提取（信号灯归属 / 路口指示牌 / 过错关键词）与判定融合。

背景：视频/照片认不出**信号灯归属**（多方向灯并存只能给 `mixed`），也认不出路口指示牌，
而这些恰是判责的关键要素；用户文字里往往写着（"我直行是绿灯，对方闯红灯左转"）。
这些要素以「用户陈述」身份进判定上下文，**检测结果优先、冲突以检测为准**，
最终结论仍由 LLM 统一辅助输出。
"""
from __future__ import annotations

from app.algo.scene_summary import build_scene_summary
from app.schemas.models import Scene
from app.services.llm import _rule_judge
from app.services.text_facts import extract_text_facts


# ---------------- 提取 ----------------

def test_extracts_light_ownership_and_red_light_claim():
    facts = extract_text_facts("我车直行通过路口是绿灯，对方闯红灯左转")

    assert facts.my_light == "green"
    assert facts.red_light_violation == "yes"
    assert facts.red_light_by == "other"


def test_opposing_lights_imply_a_red_light_run():
    """两侧灯色都写清且相反 → 等价于指认闯红灯（话里不必出现"闯"字）。"""
    facts = extract_text_facts("我方方向是绿灯，对方方向是红灯")

    assert (facts.my_light, facts.other_light) == ("green", "red")
    assert facts.red_light_violation == "yes"
    assert facts.red_light_by == "other"


def test_single_side_light_is_not_over_attributed():
    """只说"路口是红灯"没说清是谁的方向：只记命中词，不硬塞给某一方。"""
    facts = extract_text_facts("路口当时是红灯")

    assert (facts.my_light, facts.other_light) == ("unknown", "unknown")
    assert facts.red_light_violation == "unknown"
    assert "红灯" in facts.matched


def test_negation_is_respected():
    """“我没有闯红灯”不能被当成指认（否则兜底判定会直接判 yes）。"""
    facts = extract_text_facts("我没有闯红灯，对方追尾撞上来")

    assert facts.red_light_violation == "unknown"
    assert "闯红灯" not in facts.matched


def test_yellow_light_run_is_not_red_light():
    """闯黄灯 / 抢黄灯不构成闯红灯（与判定规则表一致），只算过错关键词。"""
    facts = extract_text_facts("对方抢黄灯进入路口")

    assert facts.red_light_violation == "unknown"
    assert "抢黄灯" in facts.violations


def test_extracts_signs_and_violations():
    facts = extract_text_facts("路口有禁止左转标志，对方压实线变道还逆行")

    assert "禁止左转" in facts.signs
    assert "压实线" in facts.violations
    assert "逆行" in facts.violations


def test_empty_text_yields_nothing():
    facts = extract_text_facts("")

    assert facts.matched == []
    assert facts.my_light == "unknown"


# ---------------- 摘要渲染（真正进 prompt 的那段） ----------------

def test_summary_labels_facts_as_user_statement():
    facts = extract_text_facts("我车直行是绿灯，对方闯红灯左转，路口有禁止左转标志")
    scene = Scene(scene_id="t1", source="video", text_facts=facts)

    summary = build_scene_summary(scene.model_dump())

    assert "用户陈述" in summary
    # 关键：必须标明未经检测验证，不能让人把用户口供当成检测结论
    assert "未经检测验证" in summary
    assert "以检测为准" in summary
    assert "我方方向 绿灯" in summary
    assert "指认对方闯红灯" in summary
    assert "禁止左转" in summary


def test_summary_without_facts_has_no_user_statement_block():
    scene = Scene(scene_id="t1", source="video")

    assert "用户陈述" not in build_scene_summary(scene.model_dump())


# ---------------- 规则兜底（mock / LLM 解析失败）也吃用户陈述 ----------------

def test_rule_judge_uses_user_statement_for_red_light():
    facts = extract_text_facts("我车直行是绿灯，对方闯红灯左转")

    out = _rule_judge("路口 变道 碰撞", facts.model_dump())

    assert out["red_light_violation"] == "yes"


def test_rule_judge_green_light_means_no_violation():
    facts = extract_text_facts("我车直行是绿灯")

    assert _rule_judge("追尾", facts)["red_light_violation"] == "no"


def test_rule_judge_without_facts_stays_unknown():
    assert _rule_judge("路口碰撞")["red_light_violation"] == "unknown"
