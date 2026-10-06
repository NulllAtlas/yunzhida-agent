"""
D3 判责链路验证：从 scene 事件/目标数据 → 责任判定（不依赖用户文字）。

场景：检测到 car(id=1) 与 pedestrian(id=2) 发生 collision → 应判"车撞行人"，
机动车主责、行人次责。纯逻辑，不依赖第三方包。
"""
import asyncio
import importlib.util
import os
import sys

_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Algorithm/


def _load(name, rel):
    path = os.path.join(_base, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


collision = _load("collision_mod", "core/collision.py")
rule_judge_mod = _load("rule_judge_mod", "core/rule_judge.py")
scene_summary_mod = _load("scene_summary_mod", "core/scene_summary.py")

detect_events_from_tracks = collision.detect_events_from_tracks
rule_judge = rule_judge_mod.judge
build_scene_summary = scene_summary_mod.build_scene_summary


def _pts(pairs):
    return [{"t": t, "x": x, "y": y, "w": 0.1, "h": 0.1} for t, x, y in pairs]


async def main():
    # car 撞 pedestrian
    car = _pts([(0.0, 0.8, 0.5), (2.0, 0.6, 0.5), (3.0, 0.52, 0.5)])
    ped = _pts([(0.0, 0.5, 0.55), (2.0, 0.6, 0.52), (3.0, 0.5, 0.5)])

    tracks = {1: {"points": car, "type": "car"}, 2: {"points": ped, "type": "pedestrian"}}
    events = detect_events_from_tracks(tracks)
    print("事件:", events)

    scene = {
        "source": "video",
        "road": "urban_intersection",
        "traffic_light": "red",
        "vehicles": [
            {"id": 1, "type": "car", "trajectory": car},
            {"id": 2, "type": "pedestrian", "trajectory": ped},
        ],
        "events": events,
    }

    summary = build_scene_summary(scene)
    print("\n场景摘要:\n", summary)

    result = rule_judge(summary, [], scene)
    print("\n责任判定:", result["responsibility"])
    print("依据:", result["basis"])
    print("理由:", result["reasoning"])
    print("置信度:", result["confidence"])

    assert result["responsibility"]["party_1"] == "primary"
    assert result["confidence"] > 0.5
    print("\nOK 场景数据判责链路验证通过")


if __name__ == "__main__":
    asyncio.run(main())
