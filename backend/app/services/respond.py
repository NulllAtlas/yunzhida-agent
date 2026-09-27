from app.schemas import Scene, ResponsePlan, Action


async def respond(scene: Scene, judgment, template: dict | None = None) -> ResponsePlan:
    """应急方案（骨架实现）。D5 起接入 RESPONSE-TEMPLATE。"""
    has_pedestrian = any(o.kind == "pedestrian" for o in scene.objects)
    urgent = has_pedestrian or scene.confidence < 0.4

    steps = [
        Action(order=1, action="开启双闪，熄火", urgent=False),
        Action(order=2, action="距车后方 50 米放置三角警示牌", urgent=True),
        Action(order=3, action="人员撤离至安全区域", urgent=True),
        Action(order=4, action="拨打 122 报警并留存证据", urgent=False),
    ]
    urgent_actions = [Action(order=1, action="立即拨打 120", urgent=True)] if urgent else []

    return ResponsePlan(
        emergency_level="high" if urgent else "low",
        level_label="需要立即报警/呼叫救护" if urgent else "一般事故，按步骤处置",
        urgent_actions=urgent_actions,
        steps=steps,
        insurance_note="48 小时内报保险，保存现场照片与记录仪视频",
        confidence=0.8,
    )
