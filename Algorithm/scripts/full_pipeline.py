"""
RoadMind 全链路演示（视频 → 检测 → scene → 判责 → 应急）。

一条命令跑通整个 M1→M3→M4 流程，使用 ultralytics 原生 model.track（与实测一致），
不依赖 app 包（无 pydantic 依赖），任何装有 ultralytics 的环境即可运行。

用法：
    python full_pipeline.py --source test2.mp4 --model yolov8s.pt

输出：
    scene.json          —— 符合 SCENE-SCHEMA 的场景数据
    judgment.json       —— 责任判定结果
    response.json       —— 应急方案
    控制台打印全链路结果
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

# COCO 类别 -> Scene.type
_CLS_TO_SCENE_TYPE = {
    "person": "pedestrian", "bicycle": "bicycle", "car": "car",
    "motorcycle": "motorcycle", "bus": "bus", "truck": "truck", "train": "other",
}


# ---------- 检测 + 追踪 ----------
def run_detection(model, source, fps, conf, iou, imgsz):
    tracks: dict[int, dict] = {}
    votes: dict[int, Counter] = {}
    frame_idx = 0
    for result in model.track(
        source=source, tracker="bytetrack.yaml", persist=True,
        show=False, save=False, conf=conf, iou=iou, imgsz=imgsz,
        verbose=False, stream=True,
    ):
        boxes = result.boxes
        if boxes.id is None:
            frame_idx += 1
            continue
        fw, fh = result.orig_shape[1], result.orig_shape[0]
        t = frame_idx / fps
        for cls_id, tid, xyxy in zip(boxes.cls.tolist(), boxes.id.tolist(), boxes.xyxy.tolist()):
            name = model.names[int(cls_id)]
            tid = int(tid)
            votes.setdefault(tid, Counter())[name] += 1
            x1, y1, x2, y2 = xyxy
            cx, cy = ((x1 + x2) / 2) / fw, ((y1 + y2) / 2) / fh
            w, h = (x2 - x1) / fw, (y2 - y1) / fh
            td = tracks.setdefault(tid, {"type": name, "trajectory": []})
            if not td["trajectory"] or t - td["trajectory"][-1]["t"] >= 1.0:
                td["trajectory"].append({"t": round(t, 3), "x": round(cx, 4),
                                         "y": round(cy, 4), "w": round(w, 4), "h": round(h, 4)})
        frame_idx += 1

    track_types = {tid: v.most_common(1)[0][0] for tid, v in votes.items()}
    return tracks, track_types


# ---------- 碰撞事件识别 ----------
def detect_events(tracks):
    _g = lambda p, k: p[k] if isinstance(p, dict) else getattr(p, k)
    events, ids = [], sorted(tracks.keys())
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            p, q = tracks[ids[i]], tracks[ids[j]]
            if not p["trajectory"] or not q["trajectory"]:
                continue
            md, bt, bq = 1e9, None, None
            for a in p["trajectory"]:
                for b in q["trajectory"]:
                    if abs(a["t"] - b["t"]) > 0.5:
                        continue
                    d = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
                    if d < md:
                        md, bt, bq = d, a, b
            if bt is not None and md < 0.08:
                overlap = not (bt["x"] + bt["w"] / 2 < bq["x"] - bq["w"] / 2
                               or bq["x"] + bq["w"] / 2 < bt["x"] - bt["w"] / 2
                               or bt["y"] + bt["h"] / 2 < bq["y"] - bq["h"] / 2
                               or bq["y"] + bq["h"] / 2 < bt["y"] - bt["h"] / 2)
                events.append({"time": round((bt["t"] + bq["t"]) / 2, 2),
                               "type": "collision" if overlap else "near_miss",
                               "participants": [ids[i], ids[j]],
                               "confidence": round(min(1.0, 1.0 - md * 10), 2)})
    return events


# ---------- 责任判定 ----------
def judge(scene):
    events = scene.get("events") or []
    vehicles = {v["id"]: v for v in (scene.get("vehicles") or [])}
    parts = []
    for e in events:
        if e["type"] == "collision":
            parts = e.get("participants") or []
            break
    if not parts:
        return {"responsibility": {"party_1": "unknown", "party_2": "unknown", "split": ""},
                "basis": ["要素不足"], "reasoning": ["未检测到碰撞事件"], "confidence": 0.3}
    types = [vehicles.get(p, {}).get("type", "") for p in parts]
    motor = ["car", "truck", "bus"]
    if any(t == "pedestrian" for t in types):
        mv = next((t for t in types if t in motor), "机动车")
        st = next((t for t in types if t not in motor), "行人")
        return {"responsibility": {"party_1": "primary", "party_2": "secondary", "split": "80/20"},
                "basis": ["《道交法》第47条第2款 机动车遇行人应避让"],
                "reasoning": [f"{mv}未避让行人", f"{st}未尽注意义务"], "confidence": 0.7}
    if any(t in ("motorcycle", "bicycle") for t in types):
        return {"responsibility": {"party_1": "primary", "party_2": "secondary", "split": "70/30"},
                "basis": ["《道交法》第47条", "《实施条例》第51条"],
                "reasoning": ["机动车未让行非机动车", "非机动车未尽注意义务"], "confidence": 0.65}
    return {"responsibility": {"party_1": "primary", "party_2": "secondary", "split": "70/30"},
            "basis": ["《实施条例》第51条"], "reasoning": ["一方未让行"], "confidence": 0.6}


# ---------- 应急方案 ----------
def draft_response(events, types):
    has_ped = any(types.get(p) == "pedestrian" for e in events for p in e.get("participants", []))
    if has_ped:
        return {"priority": 1,
                "steps": [{"o": 1, "a": "开启双闪停车", "u": True}, {"o": 2, "a": "拨打120急救", "u": True},
                          {"o": 3, "a": "拨打122/110报警", "u": True}, {"o": 4, "a": "放置三角牌", "u": True},
                          {"o": 5, "a": "保护现场勿移动伤员", "u": True}],
                "insurance": "同步报保险，拍现场照与全景视频。"}
    return {"priority": 2,
            "steps": [{"o": 1, "a": "开启双闪停车", "u": True}, {"o": 2, "a": "放置三角牌", "u": True},
                      {"o": 3, "a": "人员撤至安全地带", "u": True}],
            "insurance": "报保险，保留现场照片与行车记录仪。"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="视频路径")
    ap.add_argument("--model", default="yolov8s.pt", help="YOLO 权重")
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--iou", type=float, default=0.6)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--out", default="./data/outputs")
    a = ap.parse_args()

    print("=== 1. 检测+追踪 ===")
    import cv2
    from ultralytics import YOLO
    model = YOLO(a.model)
    cap = cv2.VideoCapture(a.source)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    tracks, track_types = run_detection(model, a.source, fps, a.conf, a.iou, a.imgsz)

    print("=== 2. 组装 scene ===")
    vehicles = []
    for tid, td in tracks.items():
        pts = td["trajectory"]
        ms = 0.0
        if len(pts) >= 2 and pts[-1]["t"] - pts[0]["t"] > 0:
            ms = abs(pts[-1]["x"] - pts[0]["x"]) / (pts[-1]["t"] - pts[0]["t"]) * 100.0
        vehicles.append({"id": tid, "type": _CLS_TO_SCENE_TYPE.get(track_types[tid], "other"),
                         "trajectory": pts, "max_speed_kmh": round(ms, 1)})
    scene = {"$schema": "scene.v1.json", "scene_id": Path(a.source).stem, "source": "video",
             "vehicles": vehicles, "events": detect_events(tracks), "road": "unknown",
             "lane_markings": "unknown", "traffic_light": "unknown", "visibility": "unknown",
             "confidence": 0.5}

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  目标数: {len(vehicles)}  事件: {scene['events']}")

    print("=== 3. 责任判定 ===")
    j = judge(scene)
    (out / "judgment.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {j['responsibility']}  {j['reasoning']}")

    print("=== 4. 应急方案 ===")
    r = draft_response(scene["events"], track_types)
    (out / "response.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  ", r["steps"])

    print(f"\n已输出: {out.resolve()}/scene.json judgment.json response.json")


if __name__ == "__main__":
    main()
