"""后端修改清单 B1~B4 的回归测试。

覆盖：
- B1 行车记录仪自动取证入口：按触发时刻回退"事发前 N 秒"截取片段、降级路径；
- B2 案件与车主绑定 + 双端同步推送（事件可见性 + WS 通道）；
- B3 交警下发 → 车主回执（幂等、前置检查、状态推进到 received）；
- B4 状态机扩展（forensics 起始态、received 终态、研判完成自动收敛）。
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from app.api.notifications import EventHub
from app.core.config import settings
from app.core.db import FLOW_STATUS_LABEL
from app.services.video_clip import extract_clip, probe_video, resolve_window


def _wait_done(client, task_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}/status").json()
        if task["status"] in ("done", "failed"):
            return task
        time.sleep(0.1)
    raise AssertionError("任务未在超时时间内完成")


def _login(client, username: str, role: str = "owner") -> str:
    client.post("/api/auth/register", json={"username": username, "password": "secret123", "role": role})
    return client.post("/api/auth/login", json={"username": username, "password": "secret123"}).json()["data"]["access_token"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_video(path: Path, seconds: float = 6.0, fps: float = 10.0, size=(64, 64)) -> bool:
    """用 opencv 造一段可解码的小视频；当前 opencv 构建不支持写 mp4 时返回 False。"""
    import cv2
    import numpy as np

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not writer.isOpened():
        return False
    for i in range(int(seconds * fps)):
        frame = np.full((size[1], size[0], 3), (i * 3) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return True


# ---------------- B4 状态机扩展 ----------------


def test_flow_labels_cover_forensics_and_received():
    """自动取证为起始态、车主已接收为终态，都必须有中文标签（前端直接渲染）。"""
    assert FLOW_STATUS_LABEL["forensics"]
    assert FLOW_STATUS_LABEL["received"]
    # 完整链路 自动取证→研判中→交警确认→已下发→车主已接收 的标签齐备
    for key in ("forensics", "pending_review", "decided", "dispensed", "received"):
        assert key in FLOW_STATUS_LABEL


def test_resolve_window_defaults_to_end_of_recording():
    """未显式给触发时刻时按"事故刚发生"处理：触发点取录像末尾，回退 pre 秒。"""
    start, end, trigger = resolve_window(
        trigger_s=None, duration=60.0, pre_s=30.0, post_s=5.0
    )

    assert trigger == 60.0
    assert start == 30.0
    assert end == 60.0  # 事后区间被夹到视频末尾


def test_resolve_window_clamps_out_of_range_trigger():
    start, end, trigger = resolve_window(
        trigger_s=100.0, duration=20.0, pre_s=10.0, post_s=5.0
    )

    assert trigger == 20.0
    assert start == 10.0
    assert end == 20.0


# ---------------- B1 自动取证入口 ----------------


def test_extract_clip_degrades_on_unreadable_source(tmp_path):
    """不可解码的视频不能抛异常，必须如实返回失败并清掉半成品文件。"""
    dst = tmp_path / "clip.mp4"
    meta = extract_clip(str(tmp_path / "nope.mp4"), str(dst), start_s=0.0, end_s=2.0)

    assert meta["ok"] is False
    assert meta["error"]
    assert not dst.exists()


def test_forensics_entry_extracts_pre_accident_clip(client, monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    src = tmp_path / "dashcam.mp4"
    if not _make_video(src):
        pytest.skip("当前 opencv 构建不支持写 mp4，跳过片段截取断言")

    resp = client.post(
        "/api/cases/forensics",
        data={
            "trigger_seconds": "2",
            "pre_seconds": "1",
            "post_seconds": "1",
            "device_id": "CAM-0001",
            "description": "路口追尾",
        },
        files={"video": ("dashcam.mp4", src.read_bytes(), "video/mp4")},
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    # 片段确实按 [1s, 3s] 裁出，且落在上传目录里
    clip_file = upload_dir / f"{task_id}_clip.mp4"
    assert clip_file.is_file(), "应生成取证片段"
    duration, _fps, frames, _size = probe_video(str(clip_file))
    assert frames > 0
    assert 1.5 <= duration <= 2.5, duration

    _wait_done(client, task_id)

    # 取证过程写入案件时间线（车主/交警端都能看到取了哪一段）
    timeline = client.get(f"/api/cases/{task_id}/interact").json()["data"]["timeline"]
    forensics = [t for t in timeline if t["kind"] == "forensics"]
    assert forensics, "应记录自动取证事件"
    assert "截取事发前" in forensics[0]["content"]
    assert "CAM-0001" in forensics[0]["content"]


def test_forensics_entry_starts_in_forensics_flow_and_advances(client, monkeypatch, tmp_path):
    """起始态是自动取证；研判完成后收敛到"待交警受理"（B4 全流程）。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    src = tmp_path / "d.mp4"
    if not _make_video(src):
        pytest.skip("当前 opencv 构建不支持写 mp4")

    task_id = client.post(
        "/api/cases/forensics",
        data={"trigger_seconds": "3", "pre_seconds": "2", "post_seconds": "1"},
        files={"video": ("d.mp4", src.read_bytes(), "video/mp4")},
    ).json()["task_id"]

    # 创建即处于自动取证态
    flow = client.get(f"/api/cases/{task_id}/interact").json()["data"]["flow_status"]
    assert flow == "forensics"

    _wait_done(client, task_id)
    assert client.get(f"/api/cases/{task_id}/interact").json()["data"]["flow_status"] == "pending_review"


def test_forensics_falls_back_to_raw_video_when_clip_fails(client, monkeypatch, tmp_path):
    """上传的不是真视频（截取必然失败）时也不能 500：降级用原视频继续研判。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    resp = client.post(
        "/api/cases/forensics",
        files={"video": ("dashcam.mp4", b"not-a-real-video", "video/mp4")},
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    timeline = client.get(f"/api/cases/{task_id}/interact").json()["data"]["timeline"]
    detail = next(t["content"] for t in timeline if t["kind"] == "forensics")
    assert "截取失败" in detail and "原视频" in detail

    _wait_done(client, task_id)


# ---------------- B2 案件与车主绑定 + 双端同步推送 ----------------


def test_history_scoped_to_bound_owner(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    alice = _login(client, "alice-driver")
    bob = _login(client, "bob-driver")

    mine = client.post(
        "/api/videos",
        files={"file": ("a.mp4", b"x", "video/mp4")},
        headers=_bearer(alice),
    ).json()["task_id"]
    # 匿名提交：不绑定任何车主
    anonymous = client.post(
        "/api/videos", files={"file": ("b.mp4", b"x", "video/mp4")}
    ).json()["task_id"]
    _wait_done(client, mine)
    _wait_done(client, anonymous)

    alice_ids = [r["task_id"] for r in client.get("/api/history", headers=_bearer(alice)).json()["data"]]
    bob_ids = [r["task_id"] for r in client.get("/api/history", headers=_bearer(bob)).json()["data"]]

    assert mine in alice_ids
    assert anonymous not in alice_ids, "匿名案件不属于任何车主"
    assert mine not in bob_ids, "车主之间不得互相看到对方案件"

    # 匿名查询不过滤，保持既有演示行为
    all_ids = [r["task_id"] for r in client.get("/api/history").json()["data"]]
    assert mine in all_ids and anonymous in all_ids


def test_event_hub_scopes_by_role_and_owner():
    """车主只收自己名下事件；匿名连接不收任何事件；交警收全部。"""
    hub = EventHub()

    async def scenario():
        owner_gen = hub.subscribe("owner", "alice")
        police_gen = hub.subscribe("police", "officer")
        anon_gen = hub.subscribe("anonymous", "")
        # 先把订阅跑起来（生成器体执行到 queue.get() 时订阅即已注册）
        owner_task = asyncio.create_task(owner_gen.__anext__())
        police_task = asyncio.create_task(police_gen.__anext__())
        anon_task = asyncio.create_task(anon_gen.__anext__())
        await asyncio.sleep(0)

        hub.publish({"type": "case_done", "task_id": "t1", "owner_id": "alice"})
        hub.publish({"type": "case_done", "task_id": "t2", "owner_id": "bob"})

        alice_evt = await owner_task
        police_evt = await police_task
        anon_got = anon_task.done()
        for task in (anon_task,):
            task.cancel()
        return alice_evt, police_evt, anon_got

    alice_evt, police_evt, anon_got = asyncio.run(scenario())

    assert alice_evt["task_id"] == "t1", "车主只应收自己名下案件"
    assert police_evt["task_id"] == "t1", "交警应收全部案件"
    assert anon_got is False, "匿名连接不应收到事件"


def test_notifications_ws_pushes_owner_case(client, monkeypatch, tmp_path):
    """车主端 WS：订阅后提交案件，能收到本案件的创建与完成事件（双端同步推送）。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    token = _login(client, "ws-owner")

    with client.websocket_connect(f"/api/ws/notifications?token={token}") as ws:
        time.sleep(0.1)  # 等订阅在应用事件循环里注册完成
        task_id = client.post(
            "/api/videos",
            files={"file": ("a.mp4", b"x", "video/mp4")},
            headers=_bearer(token),
        ).json()["task_id"]

        created = ws.receive_json()
        assert created["type"] == "case_created"
        assert created["task_id"] == task_id
        assert created["owner_id"] == "ws-owner"

        done = ws.receive_json()
        assert done["type"] == "case_done"
        assert done["task_id"] == task_id
        assert done["result"] is not None


# ---------------- B3 车主回执 ----------------


def _dispensed_case(client, police_token: str) -> str:
    """建案件 → 交警下发处理意见（状态到达 dispensed），返回 task_id。"""
    task_id = client.post("/api/cases", json={"text_description": "路口追尾"}).json()["task_id"]
    _wait_done(client, task_id)
    resp = client.post(
        f"/api/cases/{task_id}/police/disposition",
        json={"kind": "责令整改", "detail": "双方协商处理", "note": "注意后续保险理赔"},
        headers=_bearer(police_token),
    )
    assert resp.status_code == 200
    return task_id


def test_owner_ack_marks_received_and_is_idempotent(client, police_token):
    task_id = _dispensed_case(client, police_token)

    before = client.get(f"/api/cases/{task_id}/interact").json()["data"]
    assert before["flow_status"] == "dispensed"
    assert before["pending_ack"] == 1

    ack = client.post(f"/api/cases/{task_id}/interact/ack").json()["data"]
    assert ack["acked"] == 1
    assert ack["pending_ack"] == 0
    assert ack["flow_status"] == "received"

    after = client.get(f"/api/cases/{task_id}/interact").json()["data"]
    assert after["flow_status"] == "received"
    assert after["pending_ack"] == 0
    # 逐条带 acked_at：车主端能区分"已接收/未接收"
    assert all(t["acked_at"] for t in after["timeline"] if t["kind"] == "disposition")

    # 重复回执：幂等，不报错也不重复记录
    again = client.post(f"/api/cases/{task_id}/interact/ack").json()["data"]
    assert again["acked"] == 0
    assert again["flow_status"] == "received"


def test_ack_rejected_before_police_dispenses(client):
    """交警尚未下发时没有可回执内容，前置条件检查必须拒绝。"""
    task_id = client.post("/api/cases", json={"text_description": "追尾"}).json()["task_id"]
    _wait_done(client, task_id)

    resp = client.post(f"/api/cases/{task_id}/interact/ack")

    assert resp.status_code == 422
    assert "下发" in resp.text