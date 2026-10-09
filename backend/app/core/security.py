"""
鉴权（D7）：PBKDF2 口令哈希 + JWT（PyJWT），区分车主 / 交警角色。

- 口令用标准库 hashlib.pbkdf2_hmac（无需 bcrypt 等外部依赖）；
- 令牌用 HS256 JWT，密钥/有效期来自 settings。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.db import get_user

_ITERATIONS = 120_000
_ALGO = "pbkdf2_sha256"

# auto_error=False：缺失令牌时由我们返回统一的错误结构
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_min),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """解析令牌并返回对应用户；无效/过期/用户不存在均返回 None。

    给 WebSocket 等无法走 HTTPBearer 依赖的场景用（令牌从 query 参数传入）。
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except jwt.PyJWTError:
        return None
    user = get_user(str(payload.get("sub", "")))
    if not user:
        return None
    return {"username": user["username"], "role": user["role"]}


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict[str, Any]:
    """解析 Bearer 令牌，返回当前用户。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="缺少访问令牌")
    try:
        payload = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_alg]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="令牌已过期")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="令牌无效")
    user = get_user(str(payload.get("sub", "")))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return {"username": user["username"], "role": user["role"]}


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[dict[str, Any]]:
    """可选登录：带合法令牌时返回用户，否则返回 None（不报错）。

    用于既能匿名提交、又要在登录时把案件绑定到车主的入口（B2）。
    """
    if credentials is None:
        return None
    return decode_token(credentials.credentials)


def require_role(*roles: str) -> Callable[..., Any]:
    """生成角色校验依赖，如 Depends(require_role("police"))。"""

    async def _dep(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="当前角色无权访问该资源")
        return user

    return _dep