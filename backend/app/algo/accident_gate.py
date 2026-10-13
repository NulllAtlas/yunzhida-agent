"""确定性事故门控（纯函数，无副作用）。

"是否真实事故"由代码硬门槛判定（最高目标速度 + 最高碰撞事件置信度双门槛），
稳定、可复现，不交给 LLM 波动。

独立成模块的原因：M3 判定与 M4 应急现在是**并行**分支，两者都需要"这是不是事故"
这个结论。原先该结论藏在 judge 内部，只能靠 judge → respond 的顺序边向下游传递，
respond 一旦并行就看不到它。提成公共函数后，两条分支消费同一套规则、同一份结论。
"""
from __future__ import annotations

from app.core.config import settings


def accident_gate(scene) -> tuple[bool, str]:
    """速度与碰撞置信度双门槛。返回 (是否通过, 未通过原因)。"""
    max_speed = max((v.max_speed_kmh for v in scene.vehicles), default=0.0)
    top_conf = max(
        (e.confidence for e in scene.events if e.type == "collision"), default=0.0
    )
    if max_speed < settings.gate_min_speed_kmh:
        return False, f"最高目标速度仅 {max_speed:.1f}km/h（门槛 {settings.gate_min_speed_kmh}）"
    if top_conf < settings.gate_min_event_conf:
        return False, f"最高碰撞事件置信度仅 {top_conf:.2f}（门槛 {settings.gate_min_event_conf}）"
    return True, ""


def gate_applies(scene) -> bool:
    """是否适用门控。

    只有**真实视频检测**结果才带运动学证据：text_fallback（检测失败降级）没有检测数据，
    与纯文字/照片输入一样不能走视频门控，否则会被误判成"非事故"。
    """
    return scene is not None and scene.source == "video"


def resolve_gate(state) -> dict:
    """取门控结论：优先用 gate 节点写入的结论，缺失时按同样规则就地计算。

    节点被单独调用时（单元测试、脚本、二次调用）state 里没有 gate 键，此时自算，
    保证"单独调用"与"整图运行"的结论一致。
    """
    gate = state.get("gate")
    if gate is not None:
        return gate
    scene = state.get("scene")
    if not gate_applies(scene):
        return {"applicable": False, "passed": True, "reason": ""}
    passed, reason = accident_gate(scene)
    return {"applicable": True, "passed": passed, "reason": reason}
