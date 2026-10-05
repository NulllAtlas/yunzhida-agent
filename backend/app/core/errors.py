"""
统一错误码与异常处理（D7）。

约定：所有错误响应体统一为 `{"code": <字符串错误码>, "msg": <说明>, "data": null}`，
成功响应为 `{"code": 0, "msg": "ok", "data": ...}`（与前端 P4 已约定的格式一致）。
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """业务异常：携带字符串错误码与 HTTP 状态码。"""

    def __init__(self, code: str, msg: str, http_status: int = 400) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.http_status = http_status


def _payload(code: str, msg: str) -> dict:
    return {"code": code, "msg": msg, "data": None}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=_payload(exc.code, exc.msg))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []))
        detail = f"{loc}: {first.get('msg', '参数校验失败')}" if loc else "参数校验失败"
        return JSONResponse(status_code=422, content=_payload("VALIDATION_ERROR", detail))

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
        }.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_payload(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # 兜底：任何未捕获异常都返回统一结构，避免把栈暴露给前端
        return JSONResponse(
            status_code=500, content=_payload("INTERNAL_ERROR", f"服务内部错误：{exc}")
        )