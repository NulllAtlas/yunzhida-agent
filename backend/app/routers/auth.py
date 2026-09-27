from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class LoginReq(BaseModel):
    username: str
    password: str


class RegisterReq(BaseModel):
    username: str
    password: str
    role: str = "owner"


@router.post("/register")
async def register(req: RegisterReq):
    return {"username": req.username, "role": req.role, "message": "注册成功（待 D7 接库）"}


@router.post("/login")
async def login(req: LoginReq):
    if not req.username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    return {"token": "mock-jwt-token", "role": "police", "username": req.username}
