"""M3 判定节点：scene + 检索 → judgment。"""
from __future__ import annotations

from app.algo.accident_gate import resolve_gate
from app.algo.scene_summary import build_scene_summary, describe_text_facts
from app.graph.state import State
from app.schemas.models import Judgment, PartyRole, Responsibility
from app.services.llm import llm_service


def _non_accident_judgment(scene_id: str, reason: str) -> Judgment:
    return Judgment(
        scene_id=scene_id,
        accident_type="非事故",
        red_light_violation="unknown",
        responsibility=Responsibility(party_1="unknown", party_2="unknown", split=""),
        basis=["需补充现场要素"],
        reasoning=[f"视频感知未达到事故门槛，疑似误报：{reason}"],
        confidence=0.9,
    )


async def judge_node(state: State) -> dict:
    """返回**部分更新**（只含 judgment）。

    本节点与 respond 是并行分支：LangGraph 把返回值整体当作要提交的更新，
    若像顺序节点那样返回完整 state，两条分支就会在同一超步里重复写 case_id/scene
    等键，直接被判为 InvalidUpdateError。同理也不再写 state["step"]——
    进度由 tasks.py 的 _NODE_STEP 按节点名驱动，该字段无读者。
    """
    text = state.get("input_text", "")
    scene = state.get("scene")
    # 只有真实视频检测结果才带 scene 证据：text_fallback（检测失败降级）没有检测数据，
    # 与纯文字输入一样按用户文字判责，也绝不能走"视频来源"的事故门控。
    is_video = scene is not None and scene.source == "video"
    degraded = scene is not None and scene.source == "text_fallback"

    # 场景摘要只取自**真实检测**来源（视频 / 现场照片）。source="text" 是 mock 兜底场景，
    # 里面那"两车 12 秒追尾"是凭文字凭空造的，把它当证据喂给模型等于编造现场要素。
    detected = scene is not None and (
        scene.source in ("video", "photo") or bool(scene.photos)
    )
    scene_text = (
        build_scene_summary(scene.model_dump(), fallback_text="") if detected else ""
    )

    # 确定性门控：先由代码判定是否真实事故，未达标不走 LLM。
    # 结论优先取 gate 节点写入的那份（judge/respond 并行分支共用），单独调用本节点时就地计算。
    gate = resolve_gate(state)
    if gate["applicable"] and not gate["passed"]:
        judgment = _non_accident_judgment(state.get("case_id", "case"), gate["reason"])
        # 门控只看视频的运动学证据；用户另外附了现场照片时不能装作没看见，
        # 如实提示一句让人工复核（不改变判定）
        photo_targets = sum(len(p.targets) for p in scene.photos)
        if photo_targets:
            judgment.reasoning.append(
                f"另随附现场照片检出 {photo_targets} 个目标，未被视频门控采纳，建议人工复核"
            )
        return {"judgment": judgment}
    # 用户文字与场景证据是两份独立输入，必须同时进 prompt。
    # 原先是 `scene_text = text or 场景摘要`：只要有视频场景，用户补充的描述就被丢掉，
    # 于是"视频看不清、我补一句对方闯红灯"这种补充数据链的用法完全失效。
    if text:
        scene_text = f"{scene_text}\n用户补充描述：{text}" if scene_text else text

    # 补充文字里抽到的现场要素（信号灯归属/指示牌/过错关键词）。
    # 视频/照片场景的摘要里已经带了一段；这里只兜住摘要没走到的情况
    # （纯文字提交、检测失败降级），避免同一段话进 prompt 两遍。
    facts = scene.text_facts if scene is not None else None
    if facts is not None:
        facts_line = describe_text_facts(facts.model_dump())
        if facts_line and facts_line not in scene_text:
            scene_text = f"{scene_text}\n{facts_line}" if scene_text else facts_line

    raw = await llm_service.judge(
        scene_text, state.get("retrieved"), pre_validated=is_video, facts=facts,
    )
    reasoning = list(raw["reasoning"])
    confidence = raw["confidence"]
    if degraded:
        # 用户传了视频却没提取到有效场景：如实说明这是文字推断，
        # 不能把推断结论当成检测结果输出（否则用户无从分辨检测失败）。
        confidence = min(confidence, 0.3)
        reasoning = [
            "未能从上传的视频中提取有效场景（检测失败或文件不可读），"
            "以下结论基于文字推断，请人工复核或补录现场要素",
            *reasoning,
        ]
    return {"judgment": Judgment(
        scene_id=state.get("case_id", "case"),
        accident_type=str(raw.get("accident_type", "")),
        parties=[PartyRole(**p) for p in (raw.get("parties") or [])],
        red_light_violation=str(raw.get("red_light_violation", "unknown")),
        responsibility=Responsibility(**raw["responsibility"]),
        basis=raw["basis"],
        reasoning=reasoning,
        confidence=confidence,
    )}
