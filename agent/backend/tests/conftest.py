"""pytest 公共夹具：每个测试用独立的临时 SQLite，避免污染开发库。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import db as db_module
from app.core.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test_roadmind.db"))
    monkeypatch.setattr(settings, "use_mock", True)
    # 重置缓存的连接，确保指向新的临时库
    db_module._conn = None
    db_module.init_db()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    db_module._conn = None


@pytest.fixture()
def police_token(client) -> str:
    client.post("/api/auth/register", json={"username": "officer", "password": "secret123", "role": "police"})
    resp = client.post("/api/auth/login", json={"username": "officer", "password": "secret123"})
    return resp.json()["data"]["access_token"]