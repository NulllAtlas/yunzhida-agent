"""M4 应急节点：scene → response。

与 M3 判定是**并行**分支，所以不能依赖 judgment 传递信息——事故类型改由场景证据
（碰撞参与者目标类型 + 事件语义类型 + 碰撞几何）与用户文字推断。
"""
from __future__ import annotations

from app.algo.accident_gate import resolve_gate
from app.algo.scene_summary import build_scene_summary
from app.graph.state import State
from app.schemas.models import EmergencyResponse, ResponseStep
from app.services.llm import llm_service

# 视频感知产出的事件类型只有 collision / near_miss（见 algo/video_tracker.detect_events），
# 不含 rear_end / vehicle_pedestrian。因此事故类型必须结合碰撞参与者的目标类型
# 与碰撞形态来推断，不能只匹配事件类型字符串（那会导致视频事故永远落到通用模板）。
_PEDESTRIAN_TYPES = {"pedestrian"}


def _collision_participant_types(scene) -> set[str]:
    """碰撞事件参与者对应的目标类型集合。"""
    vehicle_types = {v.id: v.type for v in scene.vehicles}
    for event in scene.events:
        if event.type == "collision":
            return {vehicle_types.get(pid, "") for pid in event.participants}
    return set()


def _collision_geometry(scene) -> str:
    """首个带形态的碰撞事件的几何（同向 same_direction / 交叉 crossing / 斜向 oblique）。"""
    for event in scene.events:
        if event.type == "collision" and event.geometry:
            return event.geometry
    return ""


def _resolve_accident_type(scene, text: str) -> str:
    """推断应急方案类型，优先级：场景参与者 → 事件语义类型 → 碰撞形态 → 文字关键词。"""
    if scene is not None:
        if _collision_participant_types(scene) & _PEDESTRIAN_TYPES:
            # 涉及行人优先：对应"立即拨打 120"模板，是车主端最关键的提示
            return "vehicle_pedestrian"
        # 文字降级场景会直接带语义事件类型，保留兼容
        for event in scene.events:
            if event.type in ("vehicle_pedestrian", "rear_end"):
                return event.type
        # 同向碰撞即追尾形态。感知层按双方航向夹角判定（<30° 为同向，
        # 见 video_tracker.collision_geometry），不依赖 M3 判定结果，
        # 这样 M4 才能与 M3 并行。
        # 注意：一方静止时几何为 unknown，此时退回文字关键词判断（见下）。
        if _collision_geometry(scene) == "same_direction":
            return "rear_end"

    if "追尾" in text:
        return "rear_end"
    if "行人" in text or "撞人" in text:
        return "vehicle_pedestrian"
    return "general"


async def respond_node(state: State) -> dict:
    """返回**部分更新**（只含 response）。

    与 judge 是并行分支，原因同 judge_node：整体返回完整 state 会与另一条分支
    在同一超步里重复写同一个键而被拒。也不再写 state["step"]（无读者，进度见
    tasks.py 的 _NODE_STEP）。
    """
    scene = state.get("scene")
    text = state.get("input_text", "")

    # 门控已判为非事故时不产出应急方案，否则会出现"没检测到事故，却让你摆三角警示牌"
    # 这种自相矛盾的输出。依据是 gate 的确定性结论（与 M3 同源同规则），
    # 而不是 M3 的判定结果——并行时 M3 可能还没跑完。
    gate = resolve_gate(state)
    if gate["applicable"] and not gate["passed"]:
        return {"response": None}

    accident_type = _resolve_accident_type(scene, text)

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
    return {"response": EmergencyResponse(
        scene_id=state.get("case_id", "case"),
        accident_type=accident_type,
        priority=raw["priority"],
        steps=[ResponseStep(**s) for s in raw["steps"]],
        insurance=raw["insurance"],
    )}
