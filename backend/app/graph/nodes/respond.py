"""M4 应急节点：scene + judgment → response。"""
from __future__ import annotations

from app.algo.scene_summary import build_scene_summary
from app.graph.state import State
from app.schemas.models import EmergencyResponse, ResponseStep
from app.services.llm import llm_service

# 视频感知产出的事件类型只有 collision / near_miss（见 algo/video_tracker.detect_events），
# 不含 rear_end / vehicle_pedestrian。因此事故类型必须结合碰撞参与者的目标类型
# 与 M3 判定结果来推断，不能只匹配事件类型字符串（那会导致视频事故永远落到通用模板）。
_PEDESTRIAN_TYPES = {"pedestrian"}


def _collision_participant_types(scene) -> set[str]:
    """碰撞事件参与者对应的目标类型集合。"""
    vehicle_types = {v.id: v.type for v in scene.vehicles}
    for event in scene.events:
        if event.type == "collision":
            return {vehicle_types.get(pid, "") for pid in event.participants}
    return set()


def _resolve_accident_type(scene, text: str, judgment) -> str:
    """推断应急方案类型，优先级：场景参与者 → 事件语义类型 → M3 判定 → 文字关键词。"""
    if scene is not None:
        if _collision_participant_types(scene) & _PEDESTRIAN_TYPES:
            # 涉及行人优先：对应"立即拨打 120"模板，是车主端最关键的提示
            return "vehicle_pedestrian"
        # 文字降级场景会直接带语义事件类型，保留兼容
        for event in scene.events:
            if event.type in ("vehicle_pedestrian", "rear_end"):
                return event.type

    if judgment is not None and judgment.accident_type == "追尾":
        return "rear_end"
    if "追尾" in text:
        return "rear_end"
    if "行人" in text or "撞人" in text:
        return "vehicle_pedestrian"
    return "general"


async def respond_node(state: State) -> State:
    state["step"] = "responding"
    scene = state.get("scene")
    judgment = state.get("judgment")
    text = state.get("input_text", "")

    # 门控已判为非事故时不产出应急方案，否则会出现"没检测到事故，却让你摆三角警示牌"
    # 这种自相矛盾的输出（judge 与 respond 之间是无条件边，必须在这里兜住）。
    if judgment is not None and judgment.accident_type == "非事故":
        state["response"] = None
        return state

    accident_type = _resolve_accident_type(scene, text, judgment)

    template = await llm_service.draft_response(accident_type)
    # D5：非 mock 模式下用 LLM 润色步骤（失败自动原样返回模板，保证步骤不缺失）
    # 场景摘要与用户文字合并：以前是 `text or 场景`，有场景时用户补充的描述会被丢掉
    ev = (
        build_scene_summary(scene.model_dump(), fallback_text="")
        if scene is not None and (scene.source in ("video", "photo") or scene.photos)
        else ""
    )
    scene_text = f"{ev}\n用户补充描述：{text}" if ev and text else (text or ev)
    raw = await llm_service.refine_response(accident_type, scene_text, template)
    state["response"] = EmergencyResponse(
        scene_id=state.get("case_id", "case"),
        accident_type=accident_type,
        priority=raw["priority"],
        steps=[ResponseStep(**s) for s in raw["steps"]],
        insurance=raw["insurance"],
    )
    return state
