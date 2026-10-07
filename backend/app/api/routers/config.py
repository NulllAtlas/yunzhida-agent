"""运行时模型配置：在首页切换大模型，无需改 .env 重启。

流程是"先测后换"——`/llm/test` 用提交的 url/key/model 试连一次（不改动当前配置），
验证通过再由 `/llm` 应用，避免填错一个字段就把正在跑的判定链路弄挂。

**安全边界**：这组接口能改写后端正在使用的模型凭据，默认只应在**本机演示**时开放。
`ALLOW_RUNTIME_LLM_CONFIG=false` 可整体关闭（返回 403），部署到公网务必关掉。
Key 只回传掩码，绝不明文返回。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.errors import ApiError
from app.services.llm import llm_service

router = APIRouter(prefix="/api/config", tags=["config"])


class LLMConfigIn(BaseModel):
    base_url: str = Field(default="", description="OpenAI 兼容网关地址")
    api_key: str = Field(default="", description="留空表示沿用已保存的 Key")
    model: str = Field(default="", description="模型 ID")


def _mask(key: str) -> str:
    """脱敏：只保留首尾各 4 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * 6}{key[-4:]}"


def _snapshot() -> dict:
    return {
        "base_url": settings.moma_base_url,
        "model": settings.model_strong,
        "api_key_set": bool(settings.moma_api_key),
        "api_key_masked": _mask(settings.moma_api_key),
        "use_mock": settings.use_mock,
        "timeout_s": settings.llm_timeout_s,
        "editable": settings.allow_runtime_llm_config,
    }


def _require_editable() -> None:
    if not settings.allow_runtime_llm_config:
        raise ApiError(
            "LLM_CONFIG_DISABLED",
            "运行时切换模型已关闭（ALLOW_RUNTIME_LLM_CONFIG=false）",
            403,
        )


@router.get("/llm")
async def get_llm_config() -> dict:
    """当前模型配置（Key 只有掩码）。"""
    return {"code": 0, "msg": "ok", "data": _snapshot()}


@router.post("/llm/test")
async def test_llm_config(payload: LLMConfigIn) -> dict:
    """用提交的 url/key/model 试连一次，**不改动**当前配置。"""
    _require_editable()
    base_url = (payload.base_url or settings.moma_base_url).strip()
    api_key = payload.api_key or settings.moma_api_key
    model = (payload.model or settings.model_strong).strip()
    if not base_url:
        raise ApiError("MISSING_BASE_URL", "请填写网关地址", 422)
    if not model:
        raise ApiError("MISSING_MODEL", "请填写模型名称", 422)

    result = await llm_service.probe(base_url, api_key, model)
    return {
        "code": 0 if result["ok"] else -1,
        "msg": "连接成功" if result["ok"] else "连接失败",
        "data": result,
    }


@router.post("/llm")
async def set_llm_config(payload: LLMConfigIn) -> dict:
    """应用新的模型配置（**当前进程内生效**，重启后回到 .env 的值）。"""
    _require_editable()
    if payload.base_url:
        settings.moma_base_url = payload.base_url.strip()
    if payload.model:
        settings.model_strong = payload.model.strip()
        settings.model_fast = payload.model.strip()
    if payload.api_key:
        settings.moma_api_key = payload.api_key.strip()

    # 三项齐备就自动脱离 mock，让配置立刻真正生效；缺任一项则留在演示模式
    settings.use_mock = not bool(
        settings.moma_base_url and settings.moma_api_key and settings.model_strong
    )
    llm_service.reset_client()   # 丢弃缓存的客户端，下次调用用新凭据重建
    return {"code": 0, "msg": "ok", "data": _snapshot()}
