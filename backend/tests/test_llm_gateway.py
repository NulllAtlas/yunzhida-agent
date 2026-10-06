"""真实 MoMA 网关调用路径的离线验证（P2 · D4/D5/D6）。

无真实凭据时，用一个本地 OpenAI 兼容假网关替换 MoMA：验证非 mock 分支下
URL 拼接、鉴权头、模型选择、法条上下文注入、JSON 解析与失败回退。
拿到真实 Key 后只需把 .env 指向真网关，本用例即覆盖同一代码路径。
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.schemas.models import RetrievedDoc

# 假网关返回的判定结果：故意用规则兜底不会产生的值，以证明真的走了网关
_GATEWAY_JUDGMENT = {
    "responsibility": {"party_1": "equal", "party_2": "equal", "split": "60/40"},
    "basis": ["《道交法》第43条 同车道行驶后车应与前车保持安全距离"],
    "reasoning": ["由 MoMA 网关返回的判定理由"],
    "confidence": 0.91,
}


class _FakeGateway:
    """极简 OpenAI 兼容网关：POST /v1/chat/completions。"""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.mode = "ok"  # 置为 "garbage" 时返回不可解析文本，用于验证回退
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802
                size = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(size) or b"{}")
                prompt = next(
                    (m.get("content", "") for m in body.get("messages", []) if m.get("role") == "user"),
                    "",
                )
                outer.requests.append(
                    {
                        "path": self.path,
                        "authorization": self.headers.get("Authorization"),
                        "model": body.get("model"),
                        "prompt": prompt,
                    }
                )
                content = outer._render(prompt)
                payload = {
                    "id": "chatcmpl-fake",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body.get("model") or "fake",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:  # 静音访问日志
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def _render(self, prompt: str) -> str:
        if self.mode == "garbage":
            return "抱歉，我无法给出结构化结果。"
        if "应急处置助手" in prompt:  # 应急润色请求
            match = re.search(r"原始步骤：(\[.*\])", prompt, re.S)
            actions = json.loads(match.group(1)) if match else []
            return json.dumps(
                {"steps": [f"润色::{a}" for a in actions], "insurance": "已联系保险公司"},
                ensure_ascii=False,
            )
        return json.dumps(_GATEWAY_JUDGMENT, ensure_ascii=False)  # 判定请求

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture()
def gateway(monkeypatch):
    gw = _FakeGateway()
    # 避免本机代理把 127.0.0.1 也劫持走
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    from app.core.config import settings
    from app.services.llm import llm_service

    monkeypatch.setattr(settings, "use_mock", False)
    monkeypatch.setattr(settings, "moma_base_url", gw.base_url)
    monkeypatch.setattr(settings, "moma_api_key", "test-key-123")
    monkeypatch.setattr(settings, "model_strong", "test-strong")
    monkeypatch.setattr(settings, "model_fast", "test-fast")
    monkeypatch.setattr(llm_service, "_client", None)  # 丢弃可能缓存的旧客户端
    yield gw
    gw.close()


def test_judge_calls_gateway_with_auth_model_and_parses_json(gateway):
    """非 mock 下应真实请求网关，带鉴权头与强模型，并解析出判定 JSON。"""
    from app.services.llm import llm_service

    docs = [RetrievedDoc(id="law-043", title="道交法 第43条", content="保持安全距离")]
    result = asyncio.run(llm_service.judge("跟车太近发生追尾", docs))

    assert result["responsibility"]["split"] == "60/40"
    assert result["confidence"] == 0.91
    req = gateway.requests[-1]
    assert req["path"].endswith("/chat/completions")
    assert req["authorization"] == "Bearer test-key-123"
    assert req["model"] == "test-strong"
    # 法条上下文必须真的进了 prompt（_as_pairs 修复点）
    assert "保持安全距离" in req["prompt"]


def test_judge_falls_back_to_rules_on_unparsable_output(gateway):
    """网关返回不可解析文本时，必须回退规则判定而不是抛错。"""
    from app.services.llm import llm_service

    gateway.mode = "garbage"
    result = asyncio.run(llm_service.judge("跟车太近发生追尾", []))

    assert result["responsibility"]["split"] == "100/0"  # 规则兜底（追尾→100/0）
    assert result["confidence"] == 0.8


def test_refine_response_uses_gateway_but_keeps_step_count(gateway):
    """应急润色走网关，且步骤条数/顺序必须保持不变。"""
    from app.services.llm import llm_service

    template = {
        "priority": 2,
        "steps": [{"order": i + 1, "action": f"原步骤{i + 1}", "urgent": True} for i in range(4)],
        "insurance": "原保险指引",
    }
    refined = asyncio.run(llm_service.refine_response("rear_end", "追尾", template))

    assert [s["action"] for s in refined["steps"]] == [f"润色::原步骤{i + 1}" for i in range(4)]
    assert refined["insurance"] == "已联系保险公司"
    # 不应污染传入的模板
    assert template["steps"][0]["action"] == "原步骤1"


def test_pipeline_end_to_end_against_gateway(gateway, tmp_path, monkeypatch):
    """整条链路非 mock 跑一遍：判定来自网关、应急步骤被润色、任务成功。"""
    from fastapi.testclient import TestClient

    from app.core import db as db_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "db_path", str(tmp_path / "gateway.db"))
    db_module._conn = None
    db_module.init_db()
    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/cases", json={"text_description": "跟车太近发生追尾"})
        assert resp.status_code == 202
        task = _wait_done(client, resp.json()["task_id"])

    db_module._conn = None
    assert task["status"] == "done", task.get("error")
    result = task["result"]
    assert result["judgment"]["responsibility"]["split"] == "60/40"  # 来自网关而非规则
    assert result["judgment"]["confidence"] == 0.91
    assert result["response"]["accident_type"] == "rear_end"
    assert result["response"]["steps"][0]["action"].startswith("润色::")


def _wait_done(client, task_id: str, timeout: float = 30.0) -> dict:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        task = client.get(f"/api/tasks/{task_id}/status").json()
        if task["status"] in ("done", "failed"):
            return task
        time.sleep(0.1)
    raise AssertionError("任务未在超时时间内完成")