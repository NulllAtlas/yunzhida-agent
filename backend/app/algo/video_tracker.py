"""
视频检测+追踪（M1·真实检测，ultralytics 原生 track 实现）。

与 scripts/full_pipeline.py 的核心逻辑一致，供 perception 服务在
media_path 输入时调用。使用 ultralytics model.track + bytetrack，
不依赖 supervision，与你实测通过的检测方式一致。

返回符合 SCENE-SCHEMA 的 dict 形式的 scene（含碰撞事件），供责任判定消费。
"""
from __future__ import annotations

import logging
import math
from collections import Counter
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)


_CLS_TO_SCENE_TYPE = {
    "person": "pedestrian", "bicycle": "bicycle", "car": "car",
    "motorcycle": "motorcycle", "bus": "bus", "truck": "truck", "train": "other",
    "traffic light": "traffic_light", "stop sign": "stop_sign",
}

# 场景要素（非交通参与者）：它们不会与车辆发生碰撞，且检测框位置代表
# 灯头/标志牌本身而非地面位置，因此不参与碰撞事件判定。
_SCENE_ELEMENT_TYPES = {"traffic light", "stop sign"}

# 判定"目标在运动"的轨迹位移阈值（归一化坐标）
_MOVE_EPS = 0.01

# 判定"两者曾经分开过"的距离阈值：碰撞事件要求该对目标在时间重叠段内
# 至少达到过这个间距，否则视为全程贴合（重复轨迹 / 2D 投影长期重叠）。
_MIN_APPROACH = 0.10

# 两目标采样点的最大时间差：轨迹每 ~0.5s（t - last >= 0.5）取一个点，
# 容差必须小于半个采样周期，否则会把"t=0 的 A"和"t=0.5 的 B"配成一对，
# 凭空造出巨大的"位移"，让贴合的目标看起来像是曾经分开过。
# 周期上限约 0.55s（vid_stride=2 @30fps 时为 0.533s），取 0.3 有余量。
_TIME_TOL = 0.3


def _is_moving(track: dict) -> bool:
    """轨迹首末点位移是否达到运动阈值；点数不足 2 视为不可判（当作静止）。"""
    points = track["trajectory"]
    if len(points) < 2:
        return False
    return (abs(points[-1]["x"] - points[0]["x"]) >= _MOVE_EPS
            or abs(points[-1]["y"] - points[0]["y"]) >= _MOVE_EPS)


# ---------- 信号灯颜色 ----------
# HSV 阈值：亮且高饱和的像素才算灯珠，避免把整块灯壳/背景算进去
_LIGHT_MIN_LIT_PX = 4
_LIGHT_SAT_MIN = 80
_LIGHT_VAL_MIN = 120
_LIGHT_MAJORITY = 0.5


def _nearest_point(points: list[dict], t: float) -> dict | None:
    """取与时刻 t 最近的轨迹采样点（容差 _TIME_TOL 内）。"""
    best, best_d = None, _TIME_TOL
    for p in points:
        d = abs(p["t"] - t)
        if d <= best_d:
            best, best_d = p, d
    return best


def _crop_box(frame, pt: dict, fw: int, fh: int):
    """按归一化框裁剪；框太小返回 None。"""
    w, h = pt["w"] * fw, pt["h"] * fh
    x1, y1 = int(max(0, pt["x"] * fw - w / 2)), int(max(0, pt["y"] * fh - h / 2))
    x2, y2 = int(min(fw, pt["x"] * fw + w / 2)), int(min(fh, pt["y"] * fh + h / 2))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return frame[y1:y2, x1:x2]


def classify_light_color(crop) -> str | None:
    """按 HSV 判断信号灯颜色；灯珠像素太少或颜色不占多数时返回 None。

    只统计高饱和高亮的像素（灯珠本身），再按色相区间投票，
    要求某种颜色占灯珠像素的一半以上，避免把灭掉的灯也算进来。
    """
    if crop is None or getattr(crop, "size", 0) == 0:
        return None
    hue, sat, val = cv2.split(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV))
    lit = (sat > _LIGHT_SAT_MIN) & (val > _LIGHT_VAL_MIN)
    total = int(lit.sum())
    if total < _LIGHT_MIN_LIT_PX:
        return None
    h = hue[lit]
    hits = {
        "red": int(((h <= 10) | (h >= 170)).sum()),
        "green": int(((h >= 40) & (h <= 95)).sum()),
        "yellow": int(((h > 10) & (h < 40)).sum()),
    }
    state, count = max(hits.items(), key=lambda kv: kv[1])
    return state if count / total >= _LIGHT_MAJORITY else None


def aggregate_light_state(lights: list[dict]) -> str:
    """汇总路口信号灯状态。

    同一路口不同方向的红绿灯是**同时存在**的，实测一个路口能同时检出红灯
    （#3）与绿灯（#6）。因此不能简单地说"这个视频是红灯"——多色并存时返回
    "mixed"，让下游知道无法据此判定某一方闯红灯。
    """
    states = {l["state"] for l in lights if l.get("state") not in (None, "unknown")}
    if not states:
        return "unknown"
    if len(states) > 1:
        return "mixed"
    return states.pop()


# ---------- 碰撞几何 ----------
def track_heading(track: dict) -> tuple[float, float] | None:
    """轨迹的整体行进方向向量；静止或点数不足返回 None。"""
    points = track["trajectory"]
    if len(points) < 2:
        return None
    dx = points[-1]["x"] - points[0]["x"]
    dy = points[-1]["y"] - points[0]["y"]
    if (dx * dx + dy * dy) ** 0.5 < _MOVE_EPS:
        return None
    return dx, dy


def collision_geometry(first: dict, second: dict) -> str:
    """按双方行进方向的夹角区分碰撞形态。

    追尾与路口交叉碰撞的处置与责任口径完全不同（后者还牵涉信号灯），
    只看"一车动、一车停"会把交叉碰撞误归成追尾。夹角 >60° 判为交叉，
    <30° 判为同向。
    """
    h1, h2 = track_heading(first), track_heading(second)
    if h1 is None or h2 is None:
        return "unknown"        # 至少一方静止/轨迹不足，无法判形态
    dot = h1[0] * h2[0] + h1[1] * h2[1]
    norm = math.hypot(*h1) * math.hypot(*h2)
    if norm <= 0:
        return "unknown"
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot / norm))))
    if angle < 30:
        return "same_direction"
    if angle > 60:
        return "crossing"
    return "oblique"


def _max_motion_speed(points: list[dict]) -> float:
    """轨迹的峰值归一化速度。

    取相邻采样点之间的**欧氏位移**（x 与 y 同时计入）除以时间差，乘 100 缩放后取最大值。

    只算 x 方向时，纵向运动的目标（横穿的行人、迎面驶来的车辆）速度恒为 0，
    会被 judge.py 的事故门控（gate_min_speed_kmh）误判为"非事故"而漏判真实事故，
    因此两个轴都必须计入。

    注意：归一化坐标无法换算成真实车速，此值只是**相对量纲的代理指标**，
    仅供门控阈值比较，不代表真实 km/h（字段名沿用 max_speed_kmh 以兼容既有契约）。
    """
    if len(points) < 2:
        return 0.0
    best = 0.0
    for prev, cur in zip(points, points[1:]):
        dt = cur["t"] - prev["t"]
        if dt <= 0:
            continue
        dist = ((cur["x"] - prev["x"]) ** 2 + (cur["y"] - prev["y"]) ** 2) ** 0.5
        best = max(best, dist / dt * 100.0)
    return best


class VideoTracker:
    def __init__(self, model_name="yolov8s.pt", conf=0.3, iou=0.6, imgsz=640, vid_stride=2):
        self._conf, self._iou, self._imgsz = conf, iou, imgsz
        self._vid_stride = vid_stride
        from ultralytics import YOLO
        self._model = YOLO(model_name)

    def _run_track(self, source, fps):
        tracks: dict[int, dict] = {}
        votes: dict[int, Counter] = {}
        frame_idx = 0
        for result in self._model.track(
            # persist=False：整段视频在这一次调用里跑完，追踪器无需跨调用保留状态。
            # 用 persist=True 会让 ByteTrack 的内部状态泄漏到下一个视频，
            # 导致同一视频两次分析结果不一致、track ID 接着上个视频往下编。
            source=source, tracker="bytetrack.yaml", persist=False,
            show=False, save=False, conf=self._conf, iou=self._iou,
            imgsz=self._imgsz, vid_stride=self._vid_stride,
            verbose=False, stream=True,
        ):
            boxes = result.boxes
            if boxes.id is None:
                frame_idx += 1
                continue
            fw, fh = result.orig_shape[1], result.orig_shape[0]
            t = frame_idx / fps
            for cls_id, tid, xyxy in zip(boxes.cls.tolist(), boxes.id.tolist(),
                                         boxes.xyxy.tolist()):
                name = self._model.names[int(cls_id)]
                tid = int(tid)
                votes.setdefault(tid, Counter())[name] += 1
                x1, y1, x2, y2 = xyxy
                cx, cy = ((x1 + x2) / 2) / fw, ((y1 + y2) / 2) / fh
                w, h = (x2 - x1) / fw, (y2 - y1) / fh
                td = tracks.setdefault(tid, {"type": name, "trajectory": []})
                if not td["trajectory"] or t - td["trajectory"][-1]["t"] >= 0.5:
                    td["trajectory"].append({"t": round(t, 3), "x": round(cx, 4),
                                             "y": round(cy, 4), "w": round(w, 4),
                                             "h": round(h, 4)})
            frame_idx += self._vid_stride
        track_types = {tid: v.most_common(1)[0][0] for tid, v in votes.items()}
        return tracks, track_types

    def detect_events(self, tracks, min_confidence: float = 0.5):
        """碰撞事件识别（含过检过滤）。

        裸的距离阈值在密集车流里会大量误报：实测正常路口视频能检出 20+ 个
        "碰撞"，参与者还都是静止车辆（停车排队时框挨得近）。误报一旦达标，
        事故门控就会把普通视频放行成"真实事故"，并让 LLM 被迫给出事故结论。
        因此这里加五重过滤：

        - 双方轨迹点数均 <= 1：单帧闪烁的误检目标，不参与事件；
        - 双方均静止（位移 < 0.01）：静止目标之间物理上不可能碰撞；
        - 信号灯/停止标志属场景要素而非交通参与者，框位置也不代表地面位置，
          与其相关的"碰撞"无意义，直接排除；
        - 全程贴合（间距从未达到 _MIN_APPROACH）：碰撞必须意味着"接近"，
          从未分开过的目标要么是重复轨迹，要么是 2D 投影长期重叠；
        - 事件置信度低于 min_confidence 的低置信接触丢弃。
        """
        events, ids = [], sorted(tracks.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                p, q = tracks[ids[i]], tracks[ids[j]]
                if not p["trajectory"] or not q["trajectory"]:
                    continue
                if len(p["trajectory"]) <= 1 and len(q["trajectory"]) <= 1:
                    continue
                if not _is_moving(p) and not _is_moving(q):
                    continue
                if (p.get("type") in _SCENE_ELEMENT_TYPES
                        or q.get("type") in _SCENE_ELEMENT_TYPES):
                    continue

                md, bt, bq = 1e9, None, None
                far = 0.0
                seen = 0            # 共视采样点数（同一时刻能同时看到两者）
                for x in p["trajectory"]:
                    for y in q["trajectory"]:
                        # 只在"同一时刻"比较：跨时刻配对等于拿 A 的旧位置
                        # 比 B 的新位置，距离毫无物理意义。
                        if abs(x["t"] - y["t"]) > _TIME_TOL:
                            continue
                        seen += 1
                        d = ((x["x"] - y["x"]) ** 2 + (x["y"] - y["y"]) ** 2) ** 0.5
                        far = max(far, d)
                        if d < md:
                            md, bt, bq = d, x, y
                if bt is None or md >= 0.08:
                    continue
                # 碰撞意味着"接近"：两者必须曾经明显分开过。
                # 全程贴在一起的目标不构成碰撞——要么是同一辆车被追踪成了两条轨迹
                # （实测正常路口视频里 #2/#4 全程只相距 0.028 且同速同向），
                # 要么是不同景深的目标在 2D 画面上长期重叠。
                #
                # 但这条判据只在**证据足够**时成立：只有 1 个共视采样点时距离序列
                # 只有一个值，far == md 必然小于阈值，会把短轨迹全部无条件否决。
                # 实测 2.6 秒的电瓶车事故就因此被判成"无事故"（运动车 #59 撞静止车
                # #70，最近 0.021，却只有一个共视点）。点数不足时退回
                # "至少一方在运动 + 距离足够近"的自然判据。
                if seen >= 2 and far < _MIN_APPROACH:
                    continue
                overlap = not (bt["x"] + bt["w"] / 2 < bq["x"] - bq["w"] / 2
                               or bq["x"] + bq["w"] / 2 < bt["x"] - bt["w"] / 2
                               or bt["y"] + bt["h"] / 2 < bq["y"] - bq["h"] / 2
                               or bq["y"] + bq["h"] / 2 < bt["y"] - bt["h"] / 2)
                confidence = round(min(1.0, 1.0 - md * 10), 2)
                if confidence < min_confidence:
                    continue
                events.append({"time": round((bt["t"] + bq["t"]) / 2, 2),
                               "type": "collision" if overlap else "near_miss",
                               "participants": [ids[i], ids[j]],
                               "confidence": confidence,
                               "geometry": collision_geometry(p, q),
                               # 碰撞时刻双方的识别框（归一化中心+宽高）：
                               # 事故车辆是谁、框在哪，事件本身就带着
                               "boxes": [
                                   {"id": ids[i], "type": p.get("type", "car"),
                                    "x": bt.get("x", 0.0), "y": bt.get("y", 0.0),
                                    "w": bt.get("w", 0.0), "h": bt.get("h", 0.0)},
                                   {"id": ids[j], "type": q.get("type", "car"),
                                    "x": bq.get("x", 0.0), "y": bq.get("y", 0.0),
                                    "w": bq.get("w", 0.0), "h": bq.get("h", 0.0)},
                               ]})
        return events

    def _light_states(self, video_path: str, tracks: dict) -> list[dict]:
        """逐个信号灯判定颜色，返回 [{id, state, x, y}]。

        信号灯框是有的（YOLO 的 traffic light 类），但颜色从未被解析过——
        之前 scene.traffic_light 是硬编码的 "unknown"，闯红灯判定因此永远
        不可能生效。这里重放视频，逐帧裁剪灯框做 HSV 判定并按帧投票。
        """
        lights = {tid: td for tid, td in tracks.items() if td["type"] == "traffic light"}
        if not lights:
            return []
        votes: dict[int, Counter] = {tid: Counter() for tid in lights}

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % self._vid_stride == 0:
                fh, fw = frame.shape[:2]
                t = frame_idx / fps
                for tid, td in lights.items():
                    pt = _nearest_point(td["trajectory"], t)
                    if pt is None:
                        continue
                    state = classify_light_color(_crop_box(frame, pt, fw, fh))
                    if state:
                        votes[tid][state] += 1
            frame_idx += 1
        cap.release()

        out = []
        for tid, td in lights.items():
            top = votes[tid].most_common(1)
            last = td["trajectory"][-1] if td["trajectory"] else None
            out.append({
                "id": tid,
                "state": top[0][0] if top else "unknown",
                "x": last["x"] if last else 0.0,
                "y": last["y"] if last else 0.0,
            })
        return out

    # 标注框配色（BGR）：不同参与者不同颜色，一眼分清事故双方
    _BOX_COLORS = [(0, 0, 255), (0, 200, 0), (255, 160, 0), (200, 0, 200)]

    def _draw_boxes(self, frame, boxes: list[dict]) -> None:
        """在一帧上画出识别框与「#id 类型」标签（归一化框 → 像素）。"""
        fh, fw = frame.shape[:2]
        for i, b in enumerate(boxes):
            cx, cy = b.get("x", 0.0) * fw, b.get("y", 0.0) * fh
            w, h = b.get("w", 0.0) * fw, b.get("h", 0.0) * fh
            x1, y1 = int(max(0, cx - w / 2)), int(max(0, cy - h / 2))
            x2, y2 = int(min(fw - 1, cx + w / 2)), int(min(fh - 1, cy + h / 2))
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            color = self._BOX_COLORS[i % len(self._BOX_COLORS)]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"#{b.get('id', '?')} {b.get('type', '')}"
            ty = max(16, y1 - 6)
            cv2.putText(frame, label, (x1, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, color, 1, cv2.LINE_AA)

    def annotate_keyframes(self, video_path: str, events: list[dict],
                           scene_id: str, output_dir: str) -> None:
        """为每个碰撞事件生成标注关键帧：在碰撞时刻附近的采样帧上
        画出事故车辆（事件参与者）的识别框，落盘到 output_dir，
        并把文件名写回事件 keyframe 字段。

        轨迹/框都是按 vid_stride 采样的，事件 time 反推的帧号对齐到
        采样帧；重放一次视频，命中帧号时把该帧对应事件的双方框画上去。
        生成失败只记日志不抛出 —— 标注是展示增强，不能阻塞主流程。
        """
        if not events:
            return
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("annotate keyframes: cannot open video %s", video_path)
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        try:
            wanted: dict[int, list[int]] = {}
            for idx, ev in enumerate(events):
                if not (ev.get("boxes") or []):
                    continue
                frame_no = int(round(ev.get("time", 0.0) * fps / self._vid_stride))
                wanted.setdefault(max(0, frame_no) * self._vid_stride, []).append(idx)
            if not wanted:
                return
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            remaining = dict(wanted)
            frame_idx = 0
            while remaining and frame_idx <= max(remaining):
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_idx in remaining:
                    for ev_idx in remaining[frame_idx]:
                        ev = events[ev_idx]
                        self._draw_boxes(frame, ev["boxes"])
                        name = f"{scene_id}_ev{ev_idx}_t{ev.get('time', 0.0)}.jpg"
                        if cv2.imwrite(str(Path(output_dir) / name), frame):
                            ev["keyframe"] = name
                    remaining.pop(frame_idx)
                frame_idx += 1
            missed = set(remaining)
            if missed:
                logger.warning("annotate keyframes: %s events missed frames: %s",
                               len(missed), sorted(missed))
        except Exception:  # noqa: BLE001 — 标注失败不影响主流程
            logger.exception("annotate keyframes failed: %s", video_path)
        finally:
            cap.release()

    def perceive(self, video_path: str, annotate_dir: str | None = None) -> dict:
        """返回 scene 字典（dict 形式，符合 SCENE-SCHEMA）。

        annotate_dir 给出时，为碰撞事件生成标注了事故车辆识别框的关键帧。
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        tracks, track_types = self._run_track(video_path, fps)
        lights = self._light_states(video_path, tracks)
        events = self.detect_events(tracks)
        if annotate_dir:
            self.annotate_keyframes(video_path, events, Path(video_path).stem, annotate_dir)

        vehicles = []
        for tid, td in tracks.items():
            # 信号灯是场景要素不是交通参与者，单独放进 traffic_lights，
            # 免得污染"共检出目标 N 个"的计数与判责上下文
            if track_types[tid] in _SCENE_ELEMENT_TYPES:
                continue
            ms = _max_motion_speed(td["trajectory"])
            vehicles.append({"id": tid,
                             "type": _CLS_TO_SCENE_TYPE.get(track_types[tid], "other"),
                             "trajectory": td["trajectory"], "max_speed_kmh": round(ms, 1)})

        return {
            "$schema": "scene.v1.json",
            "scene_id": Path(video_path).stem,
            "source": "video",
            "vehicles": vehicles,
            "events": events,
            "traffic_lights": lights,
            "road": "unknown", "lane_markings": "unknown",
            "traffic_light": aggregate_light_state(lights), "visibility": "unknown",
            "confidence": 0.5,
        }
