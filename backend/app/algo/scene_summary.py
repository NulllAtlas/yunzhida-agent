"""
场景摘要生成：把 Scene.vehicles/events/road 等转换为供判定智能体的结构化文本描述。

让责任判定不依赖用户文字，而是从检测到的轨迹+事件数据自动推断事故类型与责任。
纯函数，无第三方依赖。

大场景（目标多/事件多）只详列置信度最高的 top_n 个碰撞事件的涉事目标，
其余汇总计数——否则 prompt 会被无关节点的描述撑爆，实测能把网关拖到 180s 超时。
"""
from __future__ import annotations

# 超过该规模即走"摘要 + 汇总"模式
_BIG_SCENE_VEHICLES = 8
_BIG_SCENE_EVENTS = 6


def _describe_one(v: dict, with_points: bool = False) -> str:
    """单个目标的描述；with_points 时附带轨迹点数（大场景下用于判断是否刚出现）。"""
    pts = v.get("trajectory", []) or []
    info = f"目标#{v.get('id')}({v.get('type', '?')})"
    if pts:
        first, last = pts[0], pts[-1]
        dx = last["x"] - first["x"]
        dy = last["y"] - first["y"]
        move = "静止" if abs(dx) < 0.01 and abs(dy) < 0.01 else (
            "向左/前" if dx < 0 else "向右/后")
        info += f" {move}，行程{abs(dx):.2f}"
        if with_points:
            info += f"，轨迹点数{len(pts)}"
    return info


def describe_vehicles(vehicles: list[dict]) -> str:
    if not vehicles:
        return "未检测到明确目标"
    return "；".join(_describe_one(v) for v in vehicles)


# 碰撞形态（M1 按双方行进方向夹角判定）的中文说明
_GEOMETRY_LABEL = {
    "same_direction": "同向（追尾/同向刮碰）",
    "crossing": "交叉（路口侧向碰撞）",
    "oblique": "斜向碰撞",
    "unknown": "形态无法判定（至少一方静止或轨迹不足）",
}


def describe_events(events: list[dict]) -> str:
    if not events:
        return "未检测到碰撞事件"
    parts = []
    for e in events:
        text = (f"t={e.get('time')}s 发生{e.get('type')}，涉及目标{e.get('participants')}"
                f"，置信度{e.get('confidence')}")
        geometry = e.get("geometry")
        if geometry:
            text += f"，形态: {_GEOMETRY_LABEL.get(geometry, geometry)}"
        parts.append(text)
    return "；".join(parts)


def describe_lights(scene: dict) -> str:
    """信号灯描述。

    同一路口不同方向的红绿灯同时存在（实测一个路口能同时检出红灯与绿灯），
    所以多色并存时必须明说——否则模型会把"存在红灯"当成"某方闯红灯"的证据。
    """
    aggregate = scene.get("traffic_light", "unknown")
    lights = scene.get("traffic_lights") or []
    if aggregate == "mixed":
        kinds = sorted({l.get("state") for l in lights
                        if l.get("state") not in (None, "unknown")})
        return (f"路口信号灯: 同时检出 {' 与 '.join(kinds)}"
                "（不同方向并存，无法据此判定某一方闯红灯）")
    if aggregate == "unknown":
        return "路口信号灯: 未能识别"
    return f"路口信号灯: {aggregate}"


# 照片检出目标类型的中文名（YOLO 类别 → 人话）
_PHOTO_TYPE_LABEL = {
    "car": "轿车", "truck": "货车", "bus": "客车", "motorcycle": "摩托车",
    "bicycle": "自行车", "pedestrian": "行人", "other": "其它目标",
}

_LIGHT_LABEL = {"red": "红灯", "green": "绿灯", "yellow": "黄灯",
                "mixed": "红绿灯并存", "unknown": "未识别"}


def describe_photos(photos: list[dict]) -> str:
    """现场照片证据描述（单帧检测：只有目标与信号灯，没有速度/方向）。

    没有照片时返回空串，调用方据此决定要不要加这一段。
    """
    if not photos:
        return ""
    parts = []
    total = 0
    for idx, photo in enumerate(photos, 1):
        targets = photo.get("targets") or []
        total += len(targets)
        if targets:
            counts: dict[str, int] = {}
            for t in targets:
                kind = _PHOTO_TYPE_LABEL.get(t.get("type", ""), t.get("type") or "目标")
                counts[kind] = counts.get(kind, 0) + 1
            kinds = "、".join(f"{k}×{v}" for k, v in sorted(counts.items()))
        else:
            kinds = "未检出可辨认目标"
        light = _LIGHT_LABEL.get(photo.get("traffic_light") or "unknown", "未识别")
        parts.append(f"照片{idx} 检出 {kinds}、信号灯 {light}")

    text = f"现场照片证据（{len(photos)} 张，共检出目标 {total} 个）: {'；'.join(parts)}"
    # 静态局限 / 检测失败原因必须原样带进 prompt，不能让模型把照片当成视频证据
    notes = sorted({p.get("note") for p in photos if p.get("note")})
    if notes:
        text += f"；说明: {'；'.join(notes)}"
    return text


def _big_scene_lines(scene: dict, vehicles: list[dict], events: list[dict],
                     top_n: int) -> list[str]:
    """大场景摘要：只详列 top_n 个最高置信度碰撞事件的涉事目标，其余只报数量。"""
    collisions = sorted(
        (e for e in events if e.get("type") == "collision"),
        key=lambda e: e.get("confidence", 0.0) or 0.0, reverse=True,
    )
    top_events = collisions[:top_n]
    involved = {p for e in top_events for p in (e.get("participants") or [])}

    described = [_describe_one(v, with_points=True) for v in vehicles if v.get("id") in involved]
    target_line = "；".join(described) if described else "未见明确涉事目标"
    others = len(vehicles) - len(involved)
    if others > 0:
        target_line += f"；另有 {others} 个与主要碰撞无关的目标"

    return [
        f"场景来源: {scene.get('source', 'unknown')}",
        f"道路: {scene.get('road', 'unknown')}",
        describe_lights(scene),
        f"共检出目标 {len(vehicles)} 个，其中主要涉事: {target_line}",
        f"主要碰撞事件: {describe_events(top_events)}",
    ]


def describe_text_facts(facts: dict | None) -> str:
    """用户补充文字里抽到的现场要素，**明确标成用户陈述**。

    检测层认不出信号灯归属（多方向灯并存 → mixed）、也认不出路口指示牌，
    这些由用户文字补上；但必须让模型知道这是用户说的、不是检测出来的 ——
    否则会把"用户声称对方闯红灯"当成检测结论。
    """
    if not facts:
        return ""
    parts: list[str] = []

    if facts.get("my_light") not in (None, "unknown") or facts.get("other_light") not in (None, "unknown"):
        parts.append(
            f"我方方向 {_LIGHT_LABEL.get(facts.get('my_light') or 'unknown', '未识别')}、"
            f"对方方向 {_LIGHT_LABEL.get(facts.get('other_light') or 'unknown', '未识别')}"
        )
    if facts.get("red_light_violation") == "yes":
        who = {"self": "我方", "other": "对方"}.get(facts.get("red_light_by") or "", "一方")
        parts.append(f"指认{who}闯红灯")
    if facts.get("signs"):
        parts.append("路口指示牌/标线: " + "、".join(facts["signs"]))
    if facts.get("violations"):
        parts.append("其他过错: " + "、".join(facts["violations"]))
    if not parts:
        return ""

    return (
        "用户陈述（由补充文字关键词提取，未经检测验证；与检测结果冲突时以检测为准）: "
        + "；".join(parts)
    )


def build_scene_summary(scene: dict | None, fallback_text: str = "",
                        top_n: int = 3) -> str:
    """
    构建场景摘要文本，供判定智能体判责。
    优先用 scene 数据；无 scene 时退回 fallback_text(用户文字)。
    """
    if not scene:
        return fallback_text or "现场要素不足，无法判定"

    vehicles = scene.get("vehicles", []) or []
    events = scene.get("events", []) or []
    photo_line = describe_photos(scene.get("photos") or [])

    if not vehicles and not events and photo_line:
        # 纯照片提交：此时只有静态证据，再输出"未检测到目标/事件"会误导模型
        lines = [
            f"场景来源: {scene.get('source', 'unknown')}",
            photo_line,
        ]
    elif len(vehicles) > _BIG_SCENE_VEHICLES or len(events) > _BIG_SCENE_EVENTS:
        lines = _big_scene_lines(scene, vehicles, events, top_n)
    else:
        lines = [
            f"场景来源: {scene.get('source', 'unknown')}",
            f"道路: {scene.get('road', 'unknown')}",
            describe_lights(scene),
            f"目标: {describe_vehicles(vehicles)}",
            f"事件: {describe_events(events)}",
        ]

    # 视频 + 照片的组合：照片证据作为补充要素追加在后面
    if photo_line and photo_line not in lines:
        lines.append(photo_line)

    # 用户陈述（信号灯归属 / 指示牌 / 过错关键词）：检测认不出的部分靠它补，
    # 但标签必须带着走，不能让人误以为这是检测结果
    facts_line = describe_text_facts(scene.get("text_facts"))
    if facts_line and facts_line not in lines:
        lines.append(facts_line)

    summary = "；".join(lines)
    # 若场景信息从检测而来（非手动文字），附加一句说明
    if scene.get("source") == "video":
        summary += "。以上要素由视频检测自动生成，请据此推断事故类型与责任"
    elif scene.get("source") == "photo":
        summary += ("。以上要素由现场照片单帧检测生成（静态画面，没有速度与方向信息），"
                    "请结合用户描述推断事故类型与责任")
    return summary
