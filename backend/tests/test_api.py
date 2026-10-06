"""后端接口与关键修复的回归测试（P2 · D2/D3/D4/D7）。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

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


def test_police_routes_reject_owner_role(client):
    client.post("/api/auth/register", json={"username": "driver", "password": "secret123", "role": "owner"})
    token = client.post("/api/auth/login", json={"username": "driver", "password": "secret123"}).json()["data"]["access_token"]
    resp = client.get("/api/cases", headers={"Authorization": f"Bearer {token}"})
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


def test_index_rules_script_runs_standalone():
    """入库脚本必须能被 `python scripts/index_rules.py` 直接执行。

    此前 sys.path[0] 是 scripts/ 而非 backend/，`import app` 直接 ModuleNotFoundError，
    即该脚本从未真正跑通过。
    """
    backend_dir = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "scripts/index_rules.py"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "入库完成" in proc.stdout, proc.stdout[-2000:]


# ---------------- 视频上传（D1/D2 缺口修复） ----------------

def _upload_dir(tmp_path, monkeypatch):
    from app.core.config import settings

    target = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", str(target))
    return target


def test_upload_video_then_create_case(client, tmp_path, monkeypatch):
    """上传视频应真实落盘并返回 video_id，且可直接用于创建案件。"""
    target = _upload_dir(tmp_path, monkeypatch)
    payload = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048

    resp = client.post("/api/uploads/video", files={"file": ("clip.mp4", payload, "video/mp4")})
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["video_id"].endswith(".mp4")
    assert data["size"] == len(payload)
    assert (target / data["video_id"]).is_file()

    # 该文件不是真实可解码视频 → 抽帧失败自动降级，但任务必须成功
    task_id = client.post("/api/cases", json={"video_id": data["video_id"]}).json()["task_id"]
    task = _wait_done(client, task_id)
    assert task["status"] == "done", task.get("error")


def test_upload_video_rejects_non_video(client, tmp_path, monkeypatch):
    target = _upload_dir(tmp_path, monkeypatch)
    resp = client.post("/api/uploads/video", files={"file": ("note.txt", b"hello", "text/plain")})
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_FILE_TYPE"
    assert not target.exists() or not any(target.iterdir())


def test_upload_video_rejects_oversize(client, tmp_path, monkeypatch):
    target = _upload_dir(tmp_path, monkeypatch)
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 1)
    big = b"\x00" * (1024 * 1024 + 16)
    resp = client.post("/api/uploads/video", files={"file": ("big.mp4", big, "video/mp4")})
    assert resp.status_code == 413
    assert resp.json()["code"] == "FILE_TOO_LARGE"
    assert not list(target.glob("*.mp4")), "超限失败不应留下半个文件"


def test_upload_video_rejects_empty(client, tmp_path, monkeypatch):
    target = _upload_dir(tmp_path, monkeypatch)
    resp = client.post("/api/uploads/video", files={"file": ("empty.mp4", b"", "video/mp4")})
    assert resp.status_code == 422
    assert resp.json()["code"] == "EMPTY_FILE"
    assert not list(target.glob("*.mp4"))