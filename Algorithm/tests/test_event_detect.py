"""
D3 碰撞事件识别逻辑验证（纯逻辑，不依赖第三方包）。

模拟两车轨迹：后车追上静止前车 → 应识别出 collision 事件；远处车不参与。
"""
import os
import sys

# 把 Algorithm/ 根目录加入 path，从 core/ 加载模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))

from core.collision import detect_events_from_tracks  # noqa: E402


def _pts(pairs):
    return [{"t": t, "x": x, "y": y, "w": 0.1, "h": 0.1} for t, x, y in pairs]


def main():
    # 车1：后车，从 x=0.8 移动到 x=0.5（追上前面的车）
    car1 = _pts([(0.0, 0.8, 0.5), (2.0, 0.6, 0.5), (3.0, 0.5, 0.5)])
    # 车2：前车，静止在 x=0.5
    car2 = _pts([(0.0, 0.5, 0.5), (2.0, 0.5, 0.5), (3.0, 0.5, 0.5)])
    # 车3：远处无关车，x=0.1，不碰撞
    car3 = _pts([(0.0, 0.1, 0.6), (2.0, 0.12, 0.6), (3.0, 0.11, 0.6)])

    tracks = {
        1: {"points": car1, "type": "car"},
        2: {"points": car2, "type": "car"},
        3: {"points": car3, "type": "car"},
    }

    events = detect_events_from_tracks(tracks)
    print("检测到事件：")
    for e in events:
        print(f"  time={e['time']} type={e['type']} participants={e['participants']} conf={e['confidence']}")

    assert events, "应至少检测到事件"
    collide = [e for e in events if e["type"] == "collision"]
    assert collide, "应检测出 collision 事件"
    assert any(3 not in e["participants"] for e in collide), "车3不应出现在碰撞事件中"
    print("\nOK 事件识别逻辑验证通过")


if __name__ == "__main__":
    main()
