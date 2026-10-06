"""云智达 后端入口。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api import auth_router, cases_router, config_router, police_router, progress_router
from app.core.config import settings
from app.core.db import init_db
from app.core.errors import register_exception_handlers
from app.core.logging import register_request_logging, setup_logging
from app.services.rag import rag_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_request_logging(app)
register_exception_handlers(app)

app.include_router(auth_router)      # D7：注册 / 登录 / JWT
app.include_router(cases_router)     # D1/D2：创建案件 / 状态 / 结果 / 指标
app.include_router(police_router)    # D7：交警端案件列表 / 详情 / 草稿导出
app.include_router(progress_router)  # D4/D5：WebSocket 进度推送
app.include_router(config_router)    # 运行时切换大模型（首页模型配置面板）

# 静态前端（打包产物 dist），便于本地一键演示
_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def index():
    index_file = _FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "云智达 API 运行中。前端未打包，请先 npm run build。"}


@app.get("/health")
async def health():
    """健康检查 + 运行配置（前端首页据此显示当前连接的模型与运行模式）。"""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": app.version,
        "use_mock": settings.use_mock,
        "rag_backend": rag_service.backend,
        "llm_configured": bool(settings.moma_base_url),
        "model_strong": settings.model_strong,
        "model_fast": settings.model_fast,
        "algo_model": settings.algo_model_name,
        "max_concurrency": settings.max_concurrency,
    }


# ==================== P4 联调占位接口 ====================
# 说明：以下两个接口是前端（P4）早期联调用的固定返回，保留是为了不破坏
# frontend/src/components/UploadZone.vue 与 views/PoliceDetail.vue 的现有调用。
# P2 的多智能体真实链路请走 `POST /api/cases` → `GET /api/tasks/{id}/result`。

class AuditReq(BaseModel):
    id: str
    action: str
    comment: str = ""


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """接收前端上传的事故照片，返回 AI 判定结果（P4 联调占位）。"""
    if not file.content_type or not file.content_type.startswith("image/"):
        return {"code": -1, "msg": "只接受图片文件", "data": None}

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        return {"code": -1, "msg": "图片超过 10MB", "data": None}

    # 模拟 AI 推理耗时
    await asyncio.sleep(1.5)

    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "fault": "甲方车辆违规变道，与正常直行的乙方车辆发生碰撞",
            "responsibility": "甲方全责",
            "confidence": 88,
            "parties": [
                {"party": "甲方车辆", "ratio": 100, "reasons": ["压实线变道", "未让直行车辆先行"]},
                {"party": "乙方车辆", "ratio": 0, "reasons": ["本车道正常直行", "无交通违法行为"]},
            ],
            "laws": [
                {
                    "clause": "《道路交通安全法实施条例》第四十四条",
                    "summary": "变更车道的机动车不得影响相关车道内行驶的机动车的正常行驶。",
                },
            ],
            "emergency": [
                "立即开启双闪（危险报警闪光灯）",
                "在来车方向 50–100 米外放置三角警示牌",
                "车上人员全部撤离到护栏外安全地带",
                "拨打 122 报警并拍照固定现场证据",
                "如有人员受伤，立即拨打 120",
            ],
        },
    }


@app.post("/api/audit")
async def audit(req: AuditReq):
    """交警审核案件（P4 联调占位）。"""
    print(f"[AUDIT] id={req.id} action={req.action} comment={req.comment}")
    return {"code": 0, "msg": f"已{req.action}", "data": {"id": req.id, "action": req.action}}


# ==================== SPA 回落 ====================
# 作用等同前端 nginx.conf 里的 `try_files $uri $uri/ /index.html`。
# 必须注册在最后：FastAPI 按注册顺序匹配，前面已注册的 API 路由优先命中。
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """非 API 的未知路径交还给前端，避免手输 `:8000/police` 拿到 404 JSON。"""
    # /api 下拼错的路径应该老实报 404，不能被前端页面盖掉，否则接口调试会非常迷惑
    if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not Found")
    if not _FRONTEND_DIR.exists():
        raise HTTPException(status_code=404, detail="前端未打包，请先 npm run build")

    # favicon.svg / icons.svg 这类根级静态文件直接返回
    root = _FRONTEND_DIR.resolve()
    candidate = (_FRONTEND_DIR / full_path).resolve()
    # resolve 之后必须仍在 dist 内：否则 /../../ 就能顺着把任意文件读出去
    if full_path and candidate.is_file() and candidate.is_relative_to(root):
        return FileResponse(candidate)
    return FileResponse(_FRONTEND_DIR / "index.html")
