from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import upload, task, result, auth, cases, ws

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = "/api/v1"
app.include_router(upload.router, prefix=api_prefix, tags=["upload"])
app.include_router(task.router, prefix=api_prefix, tags=["task"])
app.include_router(result.router, prefix=api_prefix, tags=["result"])
app.include_router(auth.router, prefix=api_prefix, tags=["auth"])
app.include_router(cases.router, prefix=api_prefix, tags=["cases"])
app.include_router(ws.router, prefix=api_prefix, tags=["ws"])


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.version}
