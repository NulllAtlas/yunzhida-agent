"""统一提交入口（视频/文字/照片）与照片证据链的回归测试。

覆盖本次改动：
1. 照片检测映射是纯函数：类别映射、归一化 bbox、"信号灯不得当成事故目标"；
2. 照片证据进场景摘要，且静态局限说明必须一起进 prompt；
3. 用户文字与场景证据**同时**进判定（原先是 `text or 场景`，有场景就丢文字）；
4. `POST /api/submissions`：三者任意组合、非法输入拒绝；
5. 提交记录（含照片名单）落后端 DB，换设备可查。
"""
from __future__ import annotations

import asyncio
import time

from app.algo.photo_detector import to_target
from app.algo.scene_summary import build_scene_summary
from app.core.config import settings
from app.graph.nodes import judge_node
from app.schemas.models import (
    PhotoEvidence,
    PhotoTarget,
    Scene,
    SceneEvent,
    Vehicle,
)
from app.services.perception import perception_service


def _run(coro):
    return asyncio.run(coro)


def _wait_done(client, task_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}/status").json()
        if task["status"] in ("done", "failed"):
            return task
        time.sleep(0.1)
    raise AssertionError("任务未在超时时间内完成")


# ---------------- 1. 照片检测映射（不依赖 YOLO 模型） ----------------


def test_photo_target_maps_class_confidence_and_normalized_bbox():
    target = to_target("truck", 0.88, [64.0, 64.0, 320.0, 192.0], 640, 640)

    assert target == {"type": "truck", "confidence": 0.88,
                      "bbox": [0.1, 0.1, 0.4, 0.2]}


def test_photo_target_skips_scene_elements():
    """信号灯/标志牌是场景要素：当成事故目标会污染"共检出目标 N 个"与判责上下文。"""
    assert to_target("traffic light", 0.9, [0.0, 0.0, 10.0, 10.0], 100, 100) is None
    assert to_target("stop sign", 0.9, [0.0, 0.0, 10.0, 10.0], 100, 100) is None


def test_photo_target_unknown_class_falls_back_to_other():
    assert to_target("fire hydrant", 0.5, [0.0, 0.0, 10.0, 10.0], 100, 100)["type"] == "other"


# ---------------- 2. 照片证据进场景摘要 ----------------


def _photo_scene() -> Scene:
    return Scene(
        scene_id="t1",
        source="photo",
        traffic_light="red",
        confidence=0.3,
        photos=[
            PhotoEvidence(
                name="现场1.jpg",
                width=1280,
                height=720,
                targets=[PhotoTarget(type="car", confidence=0.9, bbox=[0.1, 0.2, 0.3, 0.4])],
                traffic_light="red",
                note="静态画面（单帧），无法判断运动速度与方向",
            )
        ],
    )


def test_scene_summary_carries_photo_evidence_and_its_limits():
    summary = build_scene_summary(_photo_scene().model_dump())

    assert "现场照片证据" in summary
    assert "轿车×1" in summary
    assert "红灯" in summary
    # 静态局限必须进 prompt，否则模型会把照片当成视频级的运动学证据
    assert "静态画面" in summary
    assert "单帧检测" in summary


def test_scene_summary_without_photos_is_unchanged():
    """既有视频链路不能被改味：没有照片时不出现照片段。"""
    scene = Scene(
        scene_id="t2",
        source="video",
        vehicles=[Vehicle(id=1, type="car")],
        events=[SceneEvent(time=1.0, type="collision", participants=[1, 2], confidence=0.9)],
    )

    summary = build_scene_summary(scene.model_dump())

    assert "现场照片证据" not in summary
    assert "视频检测自动生成" in summary


def test_photo_only_scene_keeps_targets_out_of_vehicles(monkeypatch):
    """照片是静态证据：目标只进 photos，不能混进 vehicles（门控看的是 vehicles）。"""
    monkeypatch.setattr(settings, "use_mock", False)
    scene = perception_service._photo_scene("t1", _photo_scene().photos)

    assert scene.source == "photo"
    assert scene.vehicles == []
    assert scene.events == []
    assert len(scene.photos[0].targets) == 1


def test_photo_detection_is_not_faked_in_mock_mode(monkeypatch):
    """mock 模式不跑模型，但也不能编造检出目标：留文件名 + 说明。"""
    monkeypatch.setattr(settings, "use_mock", True)

    scene = _run(perception_service.perceive("t1", "追尾", None, ["uploads/a.jpg"]))

    assert scene.source == "photo"
    assert [p.name for p in scene.photos] == ["a.jpg"]
    assert scene.photos[0].targets == []
    assert "未做真实照片检测" in scene.photos[0].note


# ---------------- 3. 文字与场景证据同时进判定 ----------------


def _spy_judge_llm(monkeypatch) -> dict:
    """把 LLM 判定换成"记录入参"的桩，用来断言 prompt 里到底有什么。"""
    captured: dict = {}

    async def spy(scene_text, evidence, pre_validated=False, facts=None):
        captured["scene_text"] = scene_text
        captured["pre_validated"] = pre_validated
        captured["facts"] = facts
        return {
            "accident_type": "追尾",
            "parties": [{"role": "后车", "type": "car"}],
            "red_light_violation": "unknown",
            "responsibility": {"party_1": "primary", "party_2": "none", "split": "100/0"},
            "basis": ["《道交法》第43条 同车道行驶后车应与前车保持安全距离"],
            "reasoning": ["后车未保持安全距离"],
            "confidence": 0.8,
        }

    monkeypatch.setattr("app.graph.nodes.judge.llm_service.judge", spy)
    return captured


def test_judge_keeps_user_text_alongside_photo_evidence(monkeypatch):
    """照片场景 + 用户补充描述：两者都要进 prompt。

    原实现是 `scene_text = text or 场景`，只要有场景证据，用户写的那句话就被丢掉，
    "视频看不清、我补一句"这种补充数据链的用法完全失效。
    """
    captured = _spy_judge_llm(monkeypatch)
    state = {"case_id": "t1", "input_text": "对方压实线变道", "scene": _photo_scene()}

    _run(judge_node(state))

    assert "现场照片证据" in captured["scene_text"]
    assert "对方压实线变道" in captured["scene_text"]
    # 照片是弱证据：真实性仍交给 LLM 判断，不走"已由视频门控确认"的路径
    assert captured["pre_validated"] is False


def test_judge_keeps_user_text_alongside_video_evidence(monkeypatch):
    """视频场景（过了事故门控）+ 用户补充描述：同样不能丢文字。"""
    captured = _spy_judge_llm(monkeypatch)
    scene = Scene(
        scene_id="t1",
        source="video",
        vehicles=[Vehicle(id=1, type="car", max_speed_kmh=60.0)],
        events=[SceneEvent(time=1.0, type="collision", participants=[1, 2], confidence=0.9)],
        confidence=0.6,
    )
    state = {"case_id": "t1", "input_text": "对方闯红灯左转", "scene": scene}

    _run(judge_node(state))

    assert "对方闯红灯左转" in captured["scene_text"]
    assert "视频检测自动生成" in captured["scene_text"]
    assert captured["pre_validated"] is True


def test_judge_does_not_inject_mock_scene_as_evidence(monkeypatch):
    """source="text" 是 mock 兜底场景（凭文字造出"两车 12 秒追尾"），不能当证据喂模型。"""
    captured = _spy_judge_llm(monkeypatch)
    mock_scene = perception_service.mock_scene_from_text("t1", "追尾")
    state = {"case_id": "t1", "input_text": "跟车太近发生追尾", "scene": mock_scene}

    _run(judge_node(state))

    assert "场景来源" not in captured["scene_text"]
    assert "跟车太近发生追尾" in captured["scene_text"]


# ---------------- 4/5. 提交接口与后端记录 ----------------


def test_submission_with_text_and_photos(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    resp = client.post(
        "/api/submissions",
        data={"description": "对方压实线变道"},
        files=[("photos", ("现场1.jpg", b"fake-image-bytes", "image/jpeg"))],
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]
    task = _wait_done(client, task_id)
    assert task["status"] == "done", task.get("error")

    scene = task["result"]["scene"]
    assert scene["source"] == "photo"
    assert len(scene["photos"]) == 1
    assert scene["photos"][0]["targets"] == [], "mock 模式不得编造检出目标"
    assert "未做真实照片检测" in scene["photos"][0]["note"]

    # 记录落在后端：换设备/换浏览器查 /api/history 拿到的是同一份
    item = next(
        r for r in client.get("/api/history").json()["data"] if r["task_id"] == task_id
    )
    assert item["input_text"] == "对方压实线变道"
    assert len(item["photos"]) == 1


def test_submission_video_text_and_photos_together(client, monkeypatch, tmp_path):
    """三者任意组合：一次提交里视频+文字+照片都要落到记录上。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    resp = client.post(
        "/api/submissions",
        data={"description": "对方闯红灯左转"},
        files=[
            ("video", ("行车记录仪.mp4", b"not-a-real-video", "video/mp4")),
            ("photos", ("现场1.jpg", b"x", "image/jpeg")),
            ("photos", ("现场2.jpg", b"y", "image/jpeg")),
        ],
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]
    _wait_done(client, task_id)

    item = next(
        r for r in client.get("/api/history").json()["data"] if r["task_id"] == task_id
    )
    assert item["filename"] == "行车记录仪.mp4"
    assert item["input_text"] == "对方闯红灯左转"
    assert len(item["photos"]) == 2
    # 存文件名而不是绝对路径：这个字段会原样返给前端，不该泄露部署机器的目录结构
    assert all("/" not in p and "\\" not in p for p in item["photos"]), item["photos"]


def test_submission_requires_at_least_one_input(client):
    assert client.post("/api/submissions", data={"description": "   "}).status_code == 422


def test_submission_rejects_too_many_photos(client):
    files = [("photos", (f"p{i}.jpg", b"x", "image/jpeg")) for i in range(4)]

    resp = client.post("/api/submissions", files=files)

    assert resp.status_code == 422
    assert "最多" in resp.text


def test_submission_rejects_non_photo_upload(client):
    resp = client.post(
        "/api/submissions",
        files=[("photos", ("payload.exe", b"MZ", "application/octet-stream"))],
    )

    assert resp.status_code == 422
    assert "照片" in resp.text
