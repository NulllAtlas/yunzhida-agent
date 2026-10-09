"""后端接口与关键修复的回归测试（P2 · D2/D3/D4/D7）。"""
from __future__ import annotations

import time

from app.core.config import settings
from app.core.db import upsert_case
from app.services.llm import _as_pairs
from app.services.rag import RagService, _NGramEmbedding
from app.schemas.models import RetrievedDoc


# ---------------- 基础 ----------------

def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["use_mock"] is True
    assert body["rag_backend"] in ("chromadb", "keyword")


# ---------------- 主链路（D2/D4/D5） ----------------

def _wait_done(client, task_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}/status").json()
        if task["status"] in ("done", "failed"):
            return task
        time.sleep(0.1)
    raise AssertionError("任务未在超时时间内完成")


def test_pipeline_end_to_end(client):
    resp = client.post("/api/cases", json={"text_description": "路口我车直行，对方左转弯未让行发生碰撞"})
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]

    task = _wait_done(client, task_id)
    assert task["status"] == "done", task.get("error")
    assert task["progress"] == 1.0

    result = task["result"]
    assert result["case_id"] == task_id
    assert result["judgment"]["responsibility"]["party_1"] != ""
    assert result["response"]["steps"], "应急步骤不应为空"
    assert result["retrieved"], "RAG 应返回法条/案例"


def test_pipeline_rear_end_maps_to_template(client):
    task_id = client.post("/api/cases", json={"text_description": "跟车太近发生追尾"}).json()["task_id"]
    task = _wait_done(client, task_id)
    assert task["result"]["response"]["accident_type"] == "rear_end"
    assert task["result"]["judgment"]["responsibility"]["split"] == "100/0"


def test_create_case_requires_input(client):
    assert client.post("/api/cases", json={}).status_code == 422


def test_task_not_found(client):
    assert client.get("/api/tasks/does-not-exist/status").status_code == 404


def test_metrics(client):
    data = client.get("/api/metrics").json()["data"]
    assert "created" in data and "running" in data


def test_websocket_progress(client):
    task_id = client.post("/api/cases", json={"text_description": "追尾事故"}).json()["task_id"]
    _wait_done(client, task_id)  # 先等结束，保证 WS 能立刻收到终态事件

    with client.websocket_connect(f"/api/ws/tasks/{task_id}") as ws:
        events = []
        for _ in range(2):
            events.append(ws.receive_json())
        assert events[0]["type"] == "status"
        assert events[-1]["type"] == "done"
        assert events[-1]["result"]["judgment"] is not None


def test_websocket_unknown_task(client):
    with client.websocket_connect("/api/ws/tasks/nope") as ws:
        assert ws.receive_json()["type"] == "error"


# ---------------- 鉴权与交警端（D7） ----------------

def test_register_login_and_police_routes(client, police_token):
    headers = {"Authorization": f"Bearer {police_token}"}

    task_id = client.post("/api/cases", json={"text_description": "变道刮蹭"}).json()["task_id"]
    _wait_done(client, task_id)

    listed = client.get("/api/cases", headers=headers)
    assert listed.status_code == 200
    assert any(item["task_id"] == task_id for item in listed.json()["data"])

    detail = client.get(f"/api/cases/{task_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["result"]["judgment"] is not None

    draft = client.get(f"/api/cases/{task_id}/draft", headers=headers)
    assert draft.status_code == 200
    assert "道路交通事故认定书" in draft.text


def test_police_routes_reject_anonymous(client):
    assert client.get("/api/cases").status_code == 401


def test_police_reads_open_to_owner_but_writes_rejected(client):
    """交警端**读取**对任意登录用户开放（车主端要能看流转与下发内容），
    但**写操作**仍限 police 角色 —— police.py 的既有口径。

    注：本条此前断言车主读列表得 403，与 police.py 已放宽的口径矛盾（旧用例未同步）。
    """
    client.post("/api/auth/register", json={"username": "driver", "password": "secret123", "role": "owner"})
    token = client.post("/api/auth/login", json={"username": "driver", "password": "secret123"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/cases", headers=headers).status_code == 200
    # 写操作（下发消息）仍须交警角色
    resp = client.post(
        "/api/cases/driver-case/police/message", json={"content": "hi"}, headers=headers
    )
    assert resp.status_code == 403


def test_duplicate_register_conflicts(client):
    payload = {"username": "dup", "password": "secret123", "role": "owner"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret123", "role": "owner"})
    assert client.post("/api/auth/login", json={"username": "alice", "password": "wrong-pass"}).status_code == 401


# ---------------- 关键缺陷回归（D3） ----------------

def test_ngram_embedding_is_deterministic():
    """同一文本必须得到完全相同的向量（此前用内置 hash() 会随进程加盐）。"""
    emb = _NGramEmbedding()
    assert emb._encode("追尾事故") == emb._encode("追尾事故")
    assert emb("追尾事故") == emb("追尾事故")


def test_retrieve_returns_real_doc_ids():
    """检索结果的 id 不应退化成 doc-0（此前从 metadata 取 _id 恒为空）。"""
    docs = RagService().retrieve("追尾 后车未保持安全距离", top_k=3)
    assert docs, "应检索到结果"
    assert all(not d.id.startswith("doc-") for d in docs), [d.id for d in docs]
    assert all(d.title for d in docs)


def test_llm_prompt_accepts_pydantic_evidence():
    """evidence 是 RetrievedDoc 对象，early 版本按 dict 取 .get() 会静默丢上下文。"""
    docs = [RetrievedDoc(id="law-043", title="道交法 第43条", content="保持安全距离")]
    assert _as_pairs(docs) == [("道交法 第43条", "保持安全距离")]
    assert _as_pairs([{"title": "T", "content": "C"}]) == [("T", "C")]


# ---------------- 车主端研判记录（记录随后端存储，与设备无关） ----------------

def test_history_returns_records_with_full_result(client):
    """每次提交都留在后端：列表带完整结果，前端不必逐条再查详情。"""
    task_id = client.post("/api/cases", json={"text_description": "追尾事故"}).json()["task_id"]
    _wait_done(client, task_id)

    data = client.get("/api/history").json()["data"]
    item = next(r for r in data if r["task_id"] == task_id)
    assert item["status"] == "done"
    assert item["result"]["judgment"] is not None, "列表要带完整结果"
    assert item["created_at"]


def test_history_keeps_uploaded_filename(client, monkeypatch, tmp_path):
    """视频原始文件名要一起落库，列表才分得清是哪一次提交。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    resp = client.post(
        "/api/videos",
        files={"file": ("行车记录仪-追尾.MP4", b"not-a-real-video", "video/mp4")},
    )
    assert resp.status_code == 202
    task_id = resp.json()["task_id"]
    _wait_done(client, task_id)

    # 完成时那次落库不能把创建时记下的文件名冲掉（upsert 的 filename 分支）
    item = next(
        r for r in client.get("/api/history").json()["data"] if r["task_id"] == task_id
    )
    assert item["filename"] == "行车记录仪-追尾.MP4"


def test_history_marks_orphan_running_task_as_failed(client):
    """进程重启后残留的"永远跑不完"的任务必须报成中断，否则前端一直转圈。"""
    upsert_case(task_id="orphan-task", case_id="orphan-task", status="judging")

    orphan = next(
        r for r in client.get("/api/history").json()["data"] if r["task_id"] == "orphan-task"
    )
    assert orphan["status"] == "failed"
    assert "中断" in orphan["error"]