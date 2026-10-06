"""
场景摘要生成：把 Scene.vehicles/events/road 等转换为供判定智能体的结构化文本描述。

让责任判定不依赖用户文字，而是从检测到的轨迹+事件数据自动推断事故类型与责任。
纯函数，无第三方依赖。
"""
from __future__ import annotations

from typing import Any


def describe_vehicles(vehicles: list[dict]) -> str:
    if not vehicles:
        return "未检测到明确目标"
    parts = []
    for v in vehicles:
        pts = v.get("trajectory", []) or []
        info = f"目标#{v.get('id')}({v.get('type','?')})"
        if pts:
            first, last = pts[0], pts[-1]
            dx = last["x"] - first["x"]
            dy = last["y"] - first["y"]
            move = "静止" if abs(dx) < 0.01 and abs(dy) < 0.01 else (
                "向左/前" if dx < 0 else "向右/后")
            info += f" {move}，行程{abs(dx):.2f}"
        parts.append(info)
    return "；".join(parts)


def describe_events(events: list[dict]) -> str:
    if not events:
        return "未检测到碰撞事件"
    parts = []
    for e in events:
        parts.append(f"t={e.get('time')}s 发生{e.get('type')}，涉及目标{e.get('participants')}")
    return "；".join(parts)


def build_scene_summary(scene: dict | None, fallback_text: str = "") -> str:
    """
    构建场景摘要文本，供判定智能体判责。
    优先用 scene 数据；无 scene 时退回 fallback_text(用户文字)。
    """
    if not scene:
        return fallback_text or "现场要素不足，无法判定"

    lines = [
        f"场景来源: {scene.get('source', 'unknown')}",
        f"道路: {scene.get('road', 'unknown')} 信号灯: {scene.get('traffic_light', 'unknown')}",
        f"目标: {describe_vehicles(scene.get('vehicles', []) or [])}",
        f"事件: {describe_events(scene.get('events', []) or [])}",
    ]
    summary = "；".join(lines)
    # 若场景信息从检测而来（非手动文字），附加一句说明
    if scene.get("source") != "text":
        summary += "。以上要素由视频检测自动生成，请据此推断事故类型与责任"
    return summary
