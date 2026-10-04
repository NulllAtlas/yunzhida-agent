"""
full_pipeline 判责+应急逻辑验证（不跑真实视频，用模拟数据测 judge/draft_response）。
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "scripts", "full_pipeline.py")
spec = importlib.util.spec_from_file_location("fp", _path)
fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fp)

# 模拟：car 与 pedestrian 碰撞
tracks = {
    1: {"type": "car", "trajectory": [{"t": 0.0, "x": 0.8, "y": 0.5, "w": .1, "h": .1},
                                      {"t": 2.0, "x": 0.52, "y": 0.5, "w": .1, "h": .1}]},
    2: {"type": "pedestrian", "trajectory": [{"t": 0.0, "x": 0.5, "y": 0.52, "w": .1, "h": .1},
                                             {"t": 2.0, "x": 0.5, "y": 0.5, "w": .1, "h": .1}]},
}
events = fp.detect_events(tracks)
scene = {"vehicles": [{"id": k, "type": v["type"]} for k, v in tracks.items()],
         "events": events}

j = fp.judge(scene)
print("事件:", events)
print("责任判定:", j["responsibility"], "|", j["reasoning"])

r = fp.draft_response(events, {k: v["type"] for k, v in tracks.items()})
print("应急优先级:", r["priority"], "| 第一步:", r["steps"][0]["a"])

assert events and events[0]["type"] == "collision"
assert j["responsibility"]["party_1"] == "primary"
assert r["priority"] == 1  # 涉及行人 → 最高优先级
print("\nOK 全链路判责+应急逻辑验证通过")
