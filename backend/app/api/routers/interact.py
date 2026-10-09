"""双端联动路由（D12）：案件状态流转 + 交警下发消息/处理意见 + 车主查看。

- 车主端：`GET /api/cases/{task_id}/interact` 查看该案件的流转时间线与交警下发内容
  （与 /api/history 一致不做鉴权，保证车主在任意设备都能看到）；
- 交警端（需 police 角色）：
    `POST /api/cases/{task_id}/police/message`      下发消息
    `POST /api/cases/{task_id}/police/disposition`  下发处理意见（处分）
    `POST /api/cases/{task_id}/police/flow`         推进状态流转
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.db import (
    FLOW_STATUS_LABEL,
    add_case_message,
    get_case,
    get_flow_status,
    list_timeline,
    set_case_disposition,
    set_case_flow_status,
)
from app.core.errors import ApiError
from app.core.security import require_role

router = APIRouter(prefix="/api/cases", tags=["interact"])


def _ensure_case(task_id: str) -> None:
    if not get_case(task_id):
        raise ApiError("CASE_NOT_FOUND", "案件不存在", 404)


class MessageReq(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class DispositionReq(BaseModel):
    kind: str = Field("责令整改", max_length=50)  # 责令整改 / 警告 / 罚款 / 事故认定 / 其他
    detail: str = Field("", max_length=1000)
    note: str = Field("", max_length=500)


class FlowReq(BaseModel):
    action: str  # accept / approve / reject / close
    note: str = Field("", max_length=500)


_FLOW_ACTIONS: dict[str, str] = {
    "accept": "reviewing",
    "approve": "decided",
    "reject": "rejected",
    "close": "closed",
}

_FLOW_NOTE: dict[str, str] = {
    "accept": "交警已受理该案件，进入审核",
    "approve": "交警审核通过，责任认定生效",
    "reject": "交警予以驳回，请车主补充现场材料",
    "close": "案件已办结归档",
}


@router.get("/{task_id}/interact")
async def case_interact(task_id: str) -> dict[str, Any]:
    """车主端：查看案件的业务状态流转与交警下发内容。"""
    _ensure_case(task_id)
    flow = get_flow_status(task_id)
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "task_id": task_id,
            "flow_status": flow,
            "flow_label": FLOW_STATUS_LABEL.get(flow, flow),
            "timeline": list_timeline(task_id),
        },
    }


@router.post("/{task_id}/police/message")
async def police_message(
    task_id: str, body: MessageReq, _user: dict = Depends(require_role("police"))
) -> dict[str, Any]:
    """交警向车主下发消息。"""
    _ensure_case(task_id)
    add_case_message(task_id, body.content.strip())
    return {"code": 0, "msg": "ok", "data": {"sent": True}}


@router.post("/{task_id}/police/disposition")
async def police_disposition(
    task_id: str, body: DispositionReq, _user: dict = Depends(require_role("police"))
) -> dict[str, Any]:
    """交警下发处理意见（处分），并推进状态到 dispensed。"""
    _ensure_case(task_id)
    set_case_disposition(task_id, body.kind, body.detail, body.note)
    return {"code": 0, "msg": "ok", "data": {"sent": True, "flow_status": "dispensed"}}


@router.post("/{task_id}/police/flow")
async def police_flow(
    task_id: str, body: FlowReq, _user: dict = Depends(require_role("police"))
) -> dict[str, Any]:
    """交警推进案件状态流转。"""
    _ensure_case(task_id)
    target = _FLOW_ACTIONS.get(body.action)
    if not target:
        raise ApiError("VALIDATION_ERROR", f"不支持的动作：{body.action}", 422)
    set_case_flow_status(task_id, target, note=body.note or _FLOW_NOTE.get(body.action, ""))
    return {
        "code": 0,
        "msg": "ok",
        "data": {"flow_status": target, "flow_label": FLOW_STATUS_LABEL.get(target, target)},
    }
