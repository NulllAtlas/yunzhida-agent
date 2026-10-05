"""P3 感知服务适配层的离线验证（P2 · D6）。

配置 `PERCEPTION_SERVICE_URL` 时，感知应调用 P3 的 `POST /perceive` 并使用其返回的
scene；服务报错/返回非法结构/未配置时，必须回落本地降级场景且不抛错。
"""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

_REMOTE_SCENE = {
    "source": "video",
    "vehicles": [
        {
            "id": 1,
            "type": "truck",
            "max_speed_kmh": 70.0,
            "trajectory": [{"t": 0.0, "x": 0.1, "y": 0.2, "speed_kmh": 70.0}],
        }
    ],
    "events": [
        {"time": 3.5, "type": "rear_end", "participants": [1, 2],
         "keyframe": "data/frames/abc/frame_003.jpg"}
    ],
    "road": "highway",
    "lane_markings": "solid",
    "traffic_light": "unknown",
    "visibility": "night",
    "confidence": 0.77,
}


class _FakePerception:
    """极简 P3 感知服务：POST /perceive。"""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.mode = "ok"  # ok / error / garbage
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802
                size = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(size) or b"{}")
                outer.requests.append({"path": self.path, "body": body})
                if outer.mode == "error":
                    self.send_response(500)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if outer.mode == "garbage":
                    data = json.dumps({"foo": "bar"}).encode("utf-8")
                else:
                    payload = {"code": 0, "msg": "ok",
                               "data": {**_REMOTE_SCENE, "scene_id": body.get("scene_id")}}
                    data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture()
def p3(monkeypatch):
    svc = _FakePerception()
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    from app.core.config import settings

    monkeypatch.setattr(settings, "perception_service_url", svc.url)
    monkeypatch.setattr(settings, "perception_timeout_s", 5.0)
    yield svc
    svc.close()


def test_perceive_calls_p3_and_uses_remote_scene(p3):
    from app.services.perception import perception_service

    scene = asyncio.run(perception_service.perceive("case-1", "高速追尾", "/tmp/x.mp4"))

    assert scene.source == "video"
    assert scene.road == "highway"
    assert scene.visibility == "night"
    assert scene.confidence == pytest.approx(0.77)
    assert scene.vehicles[0].type == "truck"
    assert scene.events[0].keyframe.endswith("frame_003.jpg")

    req = p3.requests[-1]
    assert req["path"] == "/perceive"
    assert req["body"]["scene_id"] == "case-1"
    assert req["body"]["video_path"] == "/tmp/x.mp4"


def test_perceive_falls_back_when_service_errors(p3):
    from app.services.perception import perception_service

    p3.mode = "error"
    scene = asyncio.run(perception_service.perceive("case-2", "跟车太近发生追尾"))
    assert scene.source == "text"  # 本地降级
    assert scene.events[0].type == "rear_end"


def test_perceive_falls_back_when_service_returns_invalid(p3):
    from app.services.perception import perception_service

    p3.mode = "garbage"
    scene = asyncio.run(perception_service.perceive("case-3", "路口碰撞"))
    assert scene.source == "text"
    assert scene.scene_id == "case-3"


def test_perceive_local_when_unconfigured(monkeypatch):
    from app.core.config import settings
    from app.services.perception import perception_service

    monkeypatch.setattr(settings, "perception_service_url", "")
    scene = asyncio.run(perception_service.perceive("case-4", "路口碰撞"))
    assert scene.source == "text"
    assert scene.scene_id == "case-4"