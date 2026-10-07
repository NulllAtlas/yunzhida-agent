"""
碰撞事件识别（纯函数，无第三方依赖）。

独立放置，避免触发 app.services 包的第三方依赖，便于单元测试。
"""
from __future__ import annotations


def detect_events_from_tracks(tracks: dict[int, dict]) -> list[dict]:
    """
    碰撞事件识别：对每对目标，在时间重叠段计算归一化中心距离，
    找到最小距离（两目标接近/重叠）的时间点作为候选碰撞。

    tracks: {track_id: {"points": [{"t","x","y","w","h"}, ...]}}
    返回事件 dict 列表：[{"time","type","participants","confidence"}]
    type: collision(框重叠) / near_miss(接近未撞)
    仅对"移动目标"（车/人/二轮车）之间判断，无轨迹点者忽略。
    """
    def _g(p, k):
        # 兼容 dict 或对象访问
        return p[k] if isinstance(p, dict) else getattr(p, k)

    events: list[dict] = []
    ids = sorted(tracks.keys())

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            p, q = tracks[ids[i]], tracks[ids[j]]
            if not p["points"] or not q["points"]:
                continue

            min_dist = 1e9
            best_t = None
            bp = bq = None
            for a in p["points"]:
                for b in q["points"]:
                    if abs(_g(a, "t") - _g(b, "t")) > 0.5:
                        continue
                    d = ((_g(a, "x") - _g(b, "x")) ** 2 + (_g(a, "y") - _g(b, "y")) ** 2) ** 0.5
                    if d < min_dist:
                        min_dist = d
                        best_t = (_g(a, "t") + _g(b, "t")) / 2
                        bp, bq = a, b

            if best_t is not None and min_dist < 0.08:
                overlap = (
                    bp is not None and bq is not None
                    and not (_g(bp, "x") + _g(bp, "w") / 2 < _g(bq, "x") - _g(bq, "w") / 2
                             or _g(bq, "x") + _g(bq, "w") / 2 < _g(bp, "x") - _g(bp, "w") / 2
                             or _g(bp, "y") + _g(bp, "h") / 2 < _g(bq, "y") - _g(bq, "h") / 2
                             or _g(bq, "y") + _g(bq, "h") / 2 < _g(bp, "y") - _g(bp, "h") / 2)
                )
                events.append({
                    "time": round(best_t, 2),
                    "type": "collision" if overlap else "near_miss",
                    "participants": [ids[i], ids[j]],
                    "confidence": round(min(1.0, 1.0 - min_dist * 10), 2),
                })

    return events
