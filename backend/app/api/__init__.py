"""api 包：对外暴露各路由。"""
from app.api.routers.auth import router as auth_router
from app.api.routers.cases import router as cases_router
from app.api.routers.police import router as police_router
from app.api.routers.progress import router as progress_router

__all__ = ["auth_router", "cases_router", "police_router", "progress_router"]