"""本次缺陷修复的回归测试。

覆盖 5 个已修复的问题：
1. respond_node 的应急类型判定对视频场景永远失效（只匹配 rear_end/vehicle_pedestrian
   事件名，而视频感知只产出 collision/near_miss）；
2. 门控判"非事故"后仍产出完整应急方案；
3. 门控速度只算 x 方向，纵向运动目标速度恒为 0 而被误判为非事故；
4. 视频检测失败被静默包装成"确定结论"；
5. 后台任务未持强引用（由 TaskManager._bg_tasks 的持有方式保证，见 tasks.py）。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.algo.video_tracker import _max_motion_speed
from app.core.config import settings
from app.graph.nodes import judge_node, respond_node
from app.schemas.models import (
    Judgment,
    Responsibility,
    Scene,
    SceneEvent,
    Vehicle,
)
from app.services.perception import perception_service

# ---------------- 测试构造工具 ----------------


def _scene(source: str, events: list[SceneEvent], vehicles: list[Vehicle]) -> Scene:
    return Scene(
        scene_id="t1", source=source, vehicles=vehicles, events=events,
        road="urban_intersection", traffic_light="unknown", confidence=0.6,
    )


def _judgment(accident_type: str, confidence: float = 0.8) -> Judgment:
    return Judgment(
        scene_id="t1",
        accident_type=accident_type,
        responsibility=Responsibility(party_1="primary", party_2="none", split="100/0"),
        basis=["《道交法》第43条 同车道行驶后车应与前车保持安全距离"],
        reasoning=["后车未保持安全距离"],
        confidence=confidence,
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------- 1. 应急类型判定 ----------------


def test_respond_maps_video_pedestrian_collision(monkeypatch):
    """视频场景里车撞行人：事件名只有 collision，也必须给出"立即拨 120"的模板。

    修复前只匹配 e.type == "vehicle_pedestrian"，视频事件类型永远匹配不上，
    会落到通用模板并丢掉 120 急救步骤。
    """
    monkeypatch.setattr(settings, "use_mock", True)
    scene = _scene(
        "video",
        events=[SceneEvent(time=1.0, type="collision", participants=[1, 2], confidence=0.9)],
        vehicles=[Vehicle(id=1, type="car"), Vehicle(id=2, type="pedestrian")],
    )
    state = {"case_id": "t1", "input_text": "", "scene": scene,
             "judgment": _judgment("普通碰撞"), "step": ""}

    out = _run(respond_node(state))

    assert out["response"] is not None
    assert out["response"].accident_type == "vehicle_pedestrian"
    assert out["response"].priority == 1
    assert any("120" in s.action for s in out["response"].steps)


def test_respond_uses_judgment_for_rear_end(monkeypatch):
    """两车碰撞时类型靠 M3 判定结果（追尾）传递，M4 必须消费它。"""
    monkeypatch.setattr(settings, "use_mock", True)
    scene = _scene(
        "video",
        events=[SceneEvent(time=1.0, type="collision", participants=[1, 2], confidence=0.9)],
        vehicles=[Vehicle(id=1, type="car"), Vehicle(id=2, type="truck")],
    )
    state = {"case_id": "t1", "input_text": "", "scene": scene,
             "judgment": _judgment("追尾"), "step": ""}

    out = _run(respond_node(state))

    assert out["response"].accident_type == "rear_end"


# ---------------- 2. 非事故不出应急方案 ----------------


def test_respond_produces_no_plan_for_non_accident(monkeypatch):
    """门控判为非事故时不应给出双闪/三角牌等处置步骤（自相矛盾）。"""
    monkeypatch.setattr(settings, "use_mock", True)
    scene = _scene("video", events=[], vehicles=[Vehicle(id=1, type="car")])
    state = {"case_id": "t1", "input_text": "", "scene": scene,
             "judgment": _judgment("非事故"), "step": ""}

    out = _run(respond_node(state))

    assert out["response"] is None


# ---------------- 3. 门控速度必须计两轴 ----------------


def test_motion_speed_counts_vertical_movement():
    """只沿 y 轴运动的目标（横穿行人 / 迎面来车）速度不能再是 0。"""
    pts = [{"t": 0.0, "x": 0.5, "y": 0.2}, {"t": 1.0, "x": 0.5, "y": 0.8}]

    # 旧实现 abs(x[-1]-x[0])/Δt*100 在这里恒为 0.0，会被 gate_min_speed_kmh 判为非事故
    assert _max_motion_speed(pts) == pytest.approx(60.0)


def test_motion_speed_takes_peak_not_endpoint():
    """取相邻采样点的峰值速度：先快后停的轨迹不能被端点差抹平。"""
    pts = [
        {"t": 0.0, "x": 0.0, "y": 0.0},
        {"t": 0.5, "x": 0.4, "y": 0.0},   # 0.4/0.5*100 = 80
        {"t": 1.0, "x": 0.4, "y": 0.0},   # 静止
    ]

    assert _max_motion_speed(pts) == pytest.approx(80.0)


def test_motion_speed_handles_short_track():
    assert _max_motion_speed([]) == 0.0
    assert _max_motion_speed([{"t": 0.0, "x": 0.1, "y": 0.1}]) == 0.0


# ---------------- 4. 检测失败必须如实标注 ----------------


def test_perceive_marks_degraded_scene_when_video_unreadable(monkeypatch):
    """传了视频但检测失败：不能编造车辆/事件，必须标成 text_fallback。"""
    monkeypatch.setattr(settings, "use_mock", False)

    scene = _run(perception_service.perceive("t1", "", str(Path("no-such-video.mp4"))))

    assert scene.source == "text_fallback"
    assert scene.vehicles == []
    assert scene.events == []
    assert scene.confidence <= 0.3


def test_perceive_keeps_text_source_for_text_only_input(monkeypatch):
    """纯文字输入仍走 text 场景，不应被误标为检测失败。"""
    monkeypatch.setattr(settings, "use_mock", False)

    scene = _run(perception_service.perceive("t1", "路口两车碰撞，疑似追尾", None))

    assert scene.source == "text"
    assert scene.vehicles  # 文字场景保留 mock 目标，用于关键词兜底


def test_judge_flags_degraded_confidence(monkeypatch):
    """降级场景的判定结论必须压低置信度并说明原因，避免被当成检测结果。"""
    monkeypatch.setattr(settings, "use_mock", True)
    scene = _scene("text_fallback", events=[], vehicles=[])
    state = {"case_id": "t1", "input_text": "追尾", "scene": scene, "step": ""}

    out = _run(judge_node(state))

    judgment = out["judgment"]
    assert judgment.confidence <= 0.3
    assert "检测失败" in judgment.reasoning[0]


def test_judge_does_not_gate_text_fallback(monkeypatch):
    """降级场景没有检测数据，不能走"视频来源"的事故门控被误判为非事故。"""
    monkeypatch.setattr(settings, "use_mock", True)
    scene = _scene("text_fallback", events=[], vehicles=[])
    state = {"case_id": "t1", "input_text": "追尾", "scene": scene, "step": ""}

    out = _run(judge_node(state))

    assert out["judgment"].accident_type != "非事故"
    assert out["judgment"].responsibility.split == "100/0"


# ---------------- 5. 后台任务强引用 ----------------


def test_task_manager_keeps_strong_reference(tmp_path, monkeypatch):
    """create_task 的返回值必须被持有，否则任务可能执行途中被 GC 回收。"""
    from app.core import db as db_module

    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    monkeypatch.setattr(settings, "use_mock", True)
    db_module._conn = None
    db_module.init_db()

    from app.api.tasks import task_manager

    async def scenario():
        task_info = task_manager.create(input_text="追尾事故")
        await task_manager.run(task_info, "追尾事故")

        # run() 立即返回，此时后台任务必须已被强引用持有
        running = set(task_manager._bg_tasks)
        assert len(running) == 1
        assert all(isinstance(t, asyncio.Task) for t in running)

        await asyncio.gather(*running)
        await asyncio.sleep(0)  # 让 add_done_callback 得以执行
        return task_info

    task_info = asyncio.run(scenario())

    assert task_info.status == "done"
    assert not task_manager._bg_tasks, "任务结束后引用应被释放，避免集合无限增长"
    db_module._conn = None


# ---------------- 6. 碰撞事件过检过滤 ----------------
# 裸距离阈值在密集车流里会大量误报：实测正常路口视频检出 22 个"碰撞"，
# 参与者还全是停着排队的车。误报一旦达标，事故门控就会把普通视频放行成"真实事故"。


def _track(type_name: str, points: list[tuple[float, float, float]]):
    """points: [(t, x, y)]，宽高固定 0.1。"""
    return {
        "type": type_name,
        "trajectory": [{"t": t, "x": x, "y": y, "w": 0.1, "h": 0.1} for t, x, y in points],
    }


def _events(tracks: dict) -> list[dict]:
    from app.algo.video_tracker import VideoTracker

    return VideoTracker.__new__(VideoTracker).detect_events(tracks)


def test_detect_events_ignores_two_static_targets():
    """两个静止目标挨得再近也不可能碰撞（停车排队时的典型误报）。"""
    tracks = {
        1: _track("car", [(0.0, 0.500, 0.500), (1.0, 0.500, 0.500), (2.0, 0.501, 0.500)]),
        2: _track("car", [(0.0, 0.505, 0.500), (1.0, 0.504, 0.500), (2.0, 0.505, 0.500)]),
    }

    assert _events(tracks) == []


def test_detect_events_ignores_single_frame_targets():
    """双方都只有 1 个轨迹点 = 单帧闪烁的误检目标。"""
    tracks = {
        1: _track("car", [(0.0, 0.500, 0.500)]),
        2: _track("car", [(0.0, 0.501, 0.500)]),
    }

    assert _events(tracks) == []


def test_detect_events_ignores_scene_elements():
    """信号灯/停止标志是场景要素不是交通参与者，与其做碰撞判定无意义。"""
    tracks = {
        1: _track("car", [(0.0, 0.30, 0.50), (1.0, 0.50, 0.50)]),
        2: _track("traffic light", [(0.0, 0.50, 0.50), (1.0, 0.51, 0.50)]),
    }

    assert _events(tracks) == []


def test_detect_events_keeps_real_collision():
    """真碰撞不能被过滤掉：两台都在动的车，框重叠。"""
    tracks = {
        1: _track("car", [(0.0, 0.30, 0.50), (1.0, 0.50, 0.50)]),
        2: _track("car", [(0.0, 0.70, 0.50), (1.0, 0.505, 0.50)]),
    }

    events = _events(tracks)

    assert len(events) == 1
    assert events[0]["type"] == "collision"
    assert events[0]["participants"] == [1, 2]


def test_detect_events_drops_low_confidence():
    """置信度 = 1 - 距离*10，低于阈值（默认 0.5，即距离 > 0.05）的丢弃。"""
    from app.algo.video_tracker import VideoTracker

    vt = VideoTracker.__new__(VideoTracker)
    far = {
        1: _track("car", [(0.0, 0.30, 0.50), (1.0, 0.500, 0.50)]),
        2: _track("car", [(0.0, 0.70, 0.50), (1.0, 0.570, 0.50)]),  # 距离 0.07
    }

    assert vt.detect_events(far) == []                          # 0.07 → conf 0.3，丢弃
    assert vt.detect_events(far, min_confidence=0.2) != []      # 放宽即保留


def test_detect_events_ignores_coincident_tracks():
    """同一辆车被追踪成两条几乎重合的轨迹时，全程贴合不能算碰撞。

    实测正常路口视频里的 #2/#4：两者全程只相距 0.028，同速同向移动，
    却被裸阈值判成碰撞并把 LLM 带向了"追尾全责"。
    """
    tracks = {
        1: _track("car", [(0.0, 0.1877, 0.3646), (0.5, 0.4598, 0.3647)]),
        2: _track("car", [(0.0, 0.2155, 0.3416), (0.5, 0.4857, 0.3415)]),
    }

    assert _events(tracks) == []


def test_detect_events_ignores_single_observation_pair():
    """只被共视到一帧的两个目标：距离序列只有一个值，无从判断"接近"。"""
    tracks = {
        1: _track("car", [(0.0, 0.500, 0.500), (1.0, 0.520, 0.500)]),
        2: _track("car", [(2.0, 0.505, 0.500)]),   # 与 #1 的采样点相差 > 0.5s
    }

    assert _events(tracks) == []


def test_detect_events_requires_convergence():
    """碰撞必须意味着"接近"：先分开、后靠近才算，全程贴合不算。"""
    from app.algo.video_tracker import _MIN_APPROACH

    # 曾经分开到超过阈值、最终贴上 → 判定为碰撞
    converging = {
        1: _track("car", [(0.0, 0.20, 0.50), (1.0, 0.50, 0.50)]),
        2: _track("car", [(0.0, 0.20 + _MIN_APPROACH + 0.05, 0.50), (1.0, 0.505, 0.50)]),
    }
    assert len(_events(converging)) == 1

    # 从未分开到阈值以上、一直贴着 → 不是碰撞
    hugging = {
        1: _track("car", [(0.0, 0.200, 0.50), (1.0, 0.400, 0.50)]),
        2: _track("car", [(0.0, 0.205, 0.50), (1.0, 0.405, 0.50)]),
    }
    assert _events(hugging) == []


def test_real_rear_end_survives_filters_and_passes_gate(monkeypatch):
    """正向对照：真实追尾必须穿过全部过滤器，并让事故门控放行。

    这段过滤是"宁可错杀"的反面——如果没有这条测试，就无法证明收紧阈值之后
    真事故还能被检出（手上没有真实事故视频作对照）。
    同车道后车从 0.45 外逼近缓行前车，直到贴上。
    """
    monkeypatch.setattr(settings, "use_mock", True)
    from app.algo.video_tracker import VideoTracker

    tracks = {
        1: _track("car", [(0.0, 0.50, 0.85), (0.5, 0.50, 0.70),
                          (1.0, 0.50, 0.58), (1.5, 0.50, 0.48)]),   # 后车：逼近
        2: _track("car", [(0.0, 0.50, 0.40), (0.5, 0.50, 0.42),
                          (1.0, 0.50, 0.44), (1.5, 0.50, 0.45)]),   # 前车：缓行
    }
    events = VideoTracker.__new__(VideoTracker).detect_events(tracks)

    assert len(events) == 1, "真实追尾被误过滤"
    assert events[0]["type"] == "collision"
    assert events[0]["participants"] == [1, 2]

    # 该事件还必须是"移动目标参与"的，从而通过事故门控
    from app.algo.video_tracker import _max_motion_speed

    speeds = {tid: round(_max_motion_speed(t["trajectory"]), 1) for tid, t in tracks.items()}
    assert max(speeds.values()) >= settings.gate_min_speed_kmh, speeds
    assert events[0]["confidence"] >= settings.gate_min_event_conf, events[0]


def test_moving_vehicle_hitting_stationary_one_is_kept_with_single_overlap():
    """只有一个共视采样点时，不能因为"没看到两者分开"就否决。

    真实事故（2.6s 电瓶车闯红灯撞轿车）：运动车 #59 撞上静止车 #70，
    最近距离 0.021，但两者只有一个共视采样点。收敛判据在没有足够证据时
    必须退回自然判据，否则短轨迹会被无条件否决、整起事故判成"无事故"。
    """
    tracks = {
        59: _track("car", [(1.267, 0.5320, 0.4065), (1.8, 0.4517, 0.4071)]),
        70: _track("car", [(2.067, 0.4672, 0.4219)]),
    }

    events = _events(tracks)

    assert len(events) == 1, "运动车撞静止车被误过滤"
    assert events[0]["type"] == "collision"
    assert events[0]["participants"] == [59, 70]
    assert events[0]["confidence"] >= 0.5


def test_static_pair_still_rejected_with_single_overlap():
    """放宽的只是"证据不足"那条；两个都静止（且只有一个共视点）仍必须否决。"""
    tracks = {
        1: _track("car", [(0.0, 0.500, 0.500), (0.6, 0.500, 0.500)]),
        50: _track("car", [(0.7, 0.505, 0.501)]),   # 与 #1 只有 (0.6, 0.7) 一个共视点
    }

    assert _events(tracks) == []


# ---------------- 7. 大场景 prompt 瘦身 ----------------


def test_scene_summary_truncates_large_scene():
    """目标/事件很多时只详列涉事目标，其余只报数量，避免 prompt 撑爆网关。"""
    from app.algo.scene_summary import build_scene_summary

    vehicles = [
        {"id": i, "type": "car", "max_speed_kmh": 5.0,
         "trajectory": [{"t": 0.0, "x": 0.1 * i, "y": 0.5}, {"t": 1.0, "x": 0.1 * i, "y": 0.5}]}
        for i in range(1, 26)
    ]
    events = [
        {"time": float(i), "type": "collision", "participants": [24, 25], "confidence": 0.9}
        for i in range(22)
    ]
    scene = {"source": "video", "road": "unknown", "traffic_light": "unknown",
             "vehicles": vehicles, "events": events}

    summary = build_scene_summary(scene)

    assert "共检出目标 25 个" in summary
    assert "另有 23 个与主要碰撞无关的目标" in summary
    # 只详列 top_n=3 个事件的涉事目标（24/25），其余不在摘要里逐个出现
    assert "目标#24" in summary and "目标#25" in summary
    assert "目标#1(" not in summary
    assert len(summary) < 600


def test_scene_summary_keeps_small_scene_detail():
    """小场景不走截断，保持逐目标描述。"""
    from app.algo.scene_summary import build_scene_summary

    scene = {
        "source": "video", "road": "urban_intersection", "traffic_light": "green",
        "vehicles": [{"id": 1, "type": "car",
                      "trajectory": [{"t": 0.0, "x": 0.2, "y": 0.5}, {"t": 1.0, "x": 0.6, "y": 0.5}]}],
        "events": [{"time": 1.0, "type": "collision", "participants": [1, 2], "confidence": 0.8}],
    }

    summary = build_scene_summary(scene)

    assert "目标#1(car)" in summary
    assert "另有" not in summary


# ---------------- 8. 进度按节点开始推送 ----------------


def test_graph_emits_node_start_events(monkeypatch):
    """进度依赖 on_chain_start 在节点**执行前**触发。

    旧实现用 astream(stream_mode="values")，快照只在节点跑完后产生，
    于是判定节点里那次最耗时的 LLM 调用期间进度会一直卡在上一阶段。
    这里锁住 astream_events 的行为，langgraph 升级导致 API 变化时能立刻发现。
    """
    monkeypatch.setattr(settings, "use_mock", True)
    from app.api.tasks import _NODE_STEP
    from app.graph.builder import graph

    async def collect():
        state = {"case_id": "t", "input_text": "追尾事故", "media_path": None, "step": "pending"}
        starts = []
        async for event in graph.astream_events(state, version="v2"):
            if event["event"] == "on_chain_start" and event.get("name") in _NODE_STEP:
                starts.append(event["name"])
        return starts

    assert asyncio.run(collect()) == ["perceive", "retrieve", "judge", "respond", "aggregate"]


# ---------------- 10. 信号灯颜色与碰撞形态 ----------------


def _solid_bgr(b: int, g: int, r: int):
    import numpy as np

    img = np.zeros((12, 12, 3), dtype=np.uint8)
    img[:, :, 0], img[:, :, 1], img[:, :, 2] = b, g, r
    return img


def test_classify_light_color_reads_red_and_green():
    """信号灯颜色此前从未被解析（traffic_light 硬编码 unknown），闯红灯判定无从谈起。"""
    from app.algo.video_tracker import classify_light_color

    assert classify_light_color(_solid_bgr(0, 0, 255)) == "red"
    assert classify_light_color(_solid_bgr(0, 255, 0)) == "green"


def test_classify_light_color_rejects_dark_or_tiny():
    """灭掉的灯 / 空框不能硬凑一个颜色出来。"""
    from app.algo.video_tracker import classify_light_color

    assert classify_light_color(_solid_bgr(0, 0, 0)) is None
    assert classify_light_color(None) is None


def test_aggregate_light_state_reports_mixed():
    """同一路口红绿灯并存时必须报 mixed。

    实测一个路口能同时检出红灯(#3)与绿灯(#6)——若简单归结为"这个场景是红灯"，
    就会把"存在红灯"误当成"某方闯红灯"的证据。
    """
    from app.algo.video_tracker import aggregate_light_state

    assert aggregate_light_state([]) == "unknown"
    assert aggregate_light_state([{"state": "unknown"}]) == "unknown"
    assert aggregate_light_state([{"state": "red"}, {"state": "unknown"}]) == "red"
    assert aggregate_light_state([{"state": "red"}, {"state": "green"}]) == "mixed"


def test_collision_geometry_distinguishes_rear_end_from_crossing():
    """只看"一车动、一车停"会把路口交叉碰撞误归成追尾。"""
    from app.algo.video_tracker import collision_geometry

    same_dir = (
        _track("car", [(0.0, 0.20, 0.50), (1.0, 0.50, 0.50)]),
        _track("car", [(0.0, 0.20, 0.60), (1.0, 0.50, 0.60)]),
    )
    crossing = (
        _track("car", [(0.0, 0.20, 0.50), (1.0, 0.50, 0.50)]),
        _track("car", [(0.0, 0.60, 0.20), (1.0, 0.60, 0.50)]),
    )
    one_static = (
        _track("car", [(0.0, 0.20, 0.50), (1.0, 0.50, 0.50)]),
        _track("car", [(0.0, 0.50, 0.50), (1.0, 0.50, 0.50)]),
    )

    assert collision_geometry(*same_dir) == "same_direction"
    assert collision_geometry(*crossing) == "crossing"
    assert collision_geometry(*one_static) == "unknown"


def test_events_carry_geometry():
    """事件必须带上形态，判定提示词据此区分追尾与交叉碰撞。

    两台车行进方向垂直（一个沿 x、一个沿 y），最终在 (0.50, 0.50) 附近相撞。
    """
    tracks = {
        1: _track("car", [(0.0, 0.20, 0.50), (1.0, 0.50, 0.50)]),
        2: _track("car", [(0.0, 0.50, 0.20), (1.0, 0.50, 0.45)]),
    }

    events = _events(tracks)

    assert len(events) == 1
    assert events[0]["geometry"] == "crossing"


def test_scene_summary_spells_out_mixed_lights():
    """多色并存要在描述里明说，避免模型据此断言闯红灯。"""
    from app.algo.scene_summary import build_scene_summary

    scene = {
        "source": "video", "road": "unknown", "traffic_light": "mixed",
        "traffic_lights": [{"id": 3, "state": "red"}, {"id": 6, "state": "green"}],
        "vehicles": [], "events": [],
    }

    summary = build_scene_summary(scene)

    assert "同时检出" in summary
    assert "无法据此判定某一方闯红灯" in summary


def test_rule_fallback_sets_accident_type(monkeypatch):
    """规则兜底也必须给出事故类型。

    它原先从不设置 accident_type，导致走兜底时前端拿到空字符串，
    M4 也拿不到类型（应急方案只能落到通用模板）。
    """
    monkeypatch.setattr(settings, "use_mock", True)
    from app.services.llm import _rule_judge

    assert _rule_judge("路口两车未让行发生碰撞")["accident_type"] == "普通碰撞"
    assert _rule_judge("跟车太近发生追尾")["accident_type"] == "追尾"
    assert _rule_judge("完全无关的输入")["accident_type"] == "unknown"


# ---------------- 11. 运行时模型配置 ----------------


@pytest.fixture()
def llm_settings_guard():
    """运行时配置接口会改写全局 settings 单例，测试后必须还原。

    monkeypatch 只还原它自己设过的属性，接口内部对 settings 的赋值不会被自动回滚，
    不还原就会污染同一进程里后续所有用例。
    """
    from app.services.llm import llm_service

    saved = (settings.moma_base_url, settings.moma_api_key, settings.model_strong,
             settings.model_fast, settings.use_mock, settings.allow_runtime_llm_config)
    yield
    (settings.moma_base_url, settings.moma_api_key, settings.model_strong,
     settings.model_fast, settings.use_mock, settings.allow_runtime_llm_config) = saved
    llm_service.reset_client()


def test_llm_config_never_returns_raw_key(client, llm_settings_guard):
    """配置接口只能回传掩码，Key 绝不能明文出网。"""
    import json as _json

    settings.moma_base_url = "https://gw.example/v1"
    settings.moma_api_key = "sk-abcdefghijklmnop"
    settings.model_strong = "model-a"

    body = client.get("/api/config/llm").json()

    assert body["data"]["api_key_masked"] == "sk-a******mnop"
    assert body["data"]["api_key_set"] is True
    assert "sk-abcdefghijklmnop" not in _json.dumps(body)


def test_llm_config_apply_switches_off_mock(client, llm_settings_guard):
    """url/key/model 三项齐备后应自动脱离演示模式，否则配置不生效。"""
    resp = client.post("/api/config/llm", json={
        "base_url": "https://gw.example/v1", "api_key": "key-123456", "model": "model-b"})

    assert resp.status_code == 200
    assert settings.moma_base_url == "https://gw.example/v1"
    assert settings.model_strong == "model-b"
    assert settings.use_mock is False


def test_llm_config_apply_keeps_key_when_blank(client, llm_settings_guard):
    """前端不回填 Key（只拿到掩码），留空提交必须保留原 Key 而不是清空。"""
    settings.moma_api_key = "key-original"

    client.post("/api/config/llm", json={"base_url": "https://gw.example/v1",
                                         "api_key": "", "model": "model-c"})

    assert settings.moma_api_key == "key-original"
    assert settings.model_strong == "model-c"


def test_llm_config_disabled_returns_403(client, llm_settings_guard, monkeypatch):
    """部署到公网要能整体关掉这组接口——否则任何人都能改你的模型凭据。"""
    monkeypatch.setattr(settings, "allow_runtime_llm_config", False)

    assert client.post("/api/config/llm", json={"model": "x"}).status_code == 403
    assert client.post("/api/config/llm/test", json={"model": "x"}).status_code == 403
    assert client.get("/api/config/llm").status_code == 200   # 只读仍可


def test_llm_config_test_reports_failure_without_500(client, llm_settings_guard, monkeypatch):
    """试连失败要如实回传 ok=false，而不是把 500 抛给前端。"""
    monkeypatch.setattr(settings, "allow_runtime_llm_config", True)

    resp = client.post("/api/config/llm/test", json={
        "base_url": "http://127.0.0.1:9/v1", "api_key": "key-123456", "model": "m"})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ok"] is False
    assert data["error"]
    assert settings.moma_base_url != "http://127.0.0.1:9/v1", "试连不得改动当前配置"


def test_llm_config_test_requires_url_and_model(client, llm_settings_guard, monkeypatch):
    monkeypatch.setattr(settings, "allow_runtime_llm_config", True)
    settings.moma_base_url = ""
    settings.model_strong = ""

    assert client.post("/api/config/llm/test",
                       json={"base_url": "", "model": ""}).status_code == 422


# ---------------- 9. LLM 调用必须被墙钟硬超时切断 ----------------


class _HangingGateway:
    """模拟"收下请求但一直不吐完 body"的网关。"""

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        await asyncio.sleep(30)
        raise AssertionError("不该走到这里")


def _llm_online(monkeypatch, timeout_s: float = 0.2) -> None:
    monkeypatch.setattr(settings, "use_mock", False)
    monkeypatch.setattr(settings, "moma_base_url", "https://gateway.invalid/v1")
    monkeypatch.setattr(settings, "llm_timeout_s", timeout_s)


def test_call_chat_is_hard_bounded_by_wall_clock(monkeypatch):
    """httpx 的 read timeout 只在"完全无数据流动"时触发，网关断断续续吐字节
    就能无限期挂住（实测一次请求挂了 24 分钟）。必须由 asyncio.wait_for
    做墙钟兜底，否则 60s 的配置形同虚设。"""
    from app.services.llm import LLMService

    _llm_online(monkeypatch)
    svc = LLMService()
    monkeypatch.setattr(svc, "_get_client", lambda: _HangingGateway())

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(svc.call_chat([{"role": "user", "content": "追尾"}]))


def test_judge_falls_back_to_rules_on_timeout(monkeypatch):
    """网关超时不能让任务挂死：判定必须快速回退到规则匹配。"""
    from app.services.llm import LLMService

    _llm_online(monkeypatch)
    svc = LLMService()
    monkeypatch.setattr(svc, "_get_client", lambda: _HangingGateway())

    result = asyncio.run(svc.judge("同车道追尾，后车未保持安全距离", []))

    assert result["responsibility"]["party_1"] == "primary"
    assert result["responsibility"]["split"] == "100/0"


def test_refine_falls_back_to_template_on_timeout(monkeypatch):
    """应急步骤润色超时必须原样返回模板，步骤永不缺失。"""
    from app.services.llm import LLMService

    _llm_online(monkeypatch)
    svc = LLMService()
    monkeypatch.setattr(svc, "_get_client", lambda: _HangingGateway())

    template = asyncio.run(svc.draft_response("vehicle_pedestrian"))

    assert asyncio.run(svc.refine_response("vehicle_pedestrian", "撞到行人", template)) == template
