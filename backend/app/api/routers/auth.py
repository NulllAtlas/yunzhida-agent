"""鉴权路由（D7）：注册 / 登录，区分车主（owner）与交警（police）。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.db import create_user, get_user
from app.core.errors import ApiError
from app.core.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, description="登录名，3-32 字符")
    password: str = Field(min_length=6, max_length=64, description="密码，至少 6 位")
    role: Literal["owner", "police"] = "owner"


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=64)


@router.post("/register", status_code=201)
async def register(payload: RegisterIn) -> dict:
    """注册新用户（车主 / 交警）。"""
    if get_user(payload.username):
        raise ApiError("USER_EXISTS", "用户名已存在", 409)
    user = create_user(payload.username, hash_password(payload.password), payload.role)
    return {"code": 0, "msg": "ok", "data": user}


@router.post("/login")
async def login(payload: LoginIn) -> dict:
    """登录换取 JWT。"""
    user = get_user(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise ApiError("BAD_CREDENTIALS", "用户名或密码错误", 401)
    token = create_token(user["username"], user["role"])
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "role": user["role"],
            "expires_in": settings.jwt_expire_min * 60,
        },
    }