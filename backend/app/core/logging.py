"""日志配置（D7/D8）：统一格式与级别，便于排查线上问题。"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request

from app.core.config import settings

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format=_FORMAT,
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def register_request_logging(app: FastAPI) -> None:
    """记录每次请求的方法/路径/状态码/耗时（节流：健康检查不记录）。"""
    logger = logging.getLogger("roadmind.access")

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        cost_ms = (time.perf_counter() - start) * 1000
        if request.url.path != "/health":
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                cost_ms,
            )
        response.headers["X-Process-Time-ms"] = f"{cost_ms:.1f}"
        return response