"""交警端路由（D7）：案件列表 / 案件详情 / 认定书草稿导出。

案件数据来自 SQLite（由 TaskManager 在多智能体流水线完成后写入）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.core.db import get_case, list_cases
from app.core.errors import ApiError
from app.core.security import require_role

router = APIRouter(prefix="/api/cases", tags=["police"])

_PARTY_LABEL = {
    "primary": "主要责任",
    "secondary": "次要责任",
    "equal": "同等责任",
    "none": "无责任",
    "unknown": "待补充认定",
}


@router.get("")
async def cases(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _user: dict = Depends(require_role("police")),
) -> dict:
    """交警端案件列表（摘要）。"""
    return {"code": 0, "msg": "ok", "data": list_cases(limit=limit, offset=offset)}


@router.get("/{task_id}")
async def case_detail(task_id: str, _user: dict = Depends(require_role("police"))) -> dict:
    """案件详情（含完整判定与应急结果）。"""
    case = get_case(task_id)
    if not case:
        raise ApiError("CASE_NOT_FOUND", "案件不存在", 404)
    return {"code": 0, "msg": "ok", "data": case}


@router.get("/{task_id}/draft", response_class=PlainTextResponse)
async def case_draft(task_id: str, _user: dict = Depends(require_role("police"))) -> PlainTextResponse:
    """导出《道路交通事故认定书（草稿）》纯文本。"""
    case = get_case(task_id)
    if not case:
        raise ApiError("CASE_NOT_FOUND", "案件不存在", 404)

    result = case.get("result") or {}
    judgment = result.get("judgment") or {}
    response = result.get("response") or {}
    resp = judgment.get("responsibility") or {}

    lines: list[str] = [
        "道路交通事故认定书（草稿）",
        "=" * 32,
        f"案件编号：{case.get('case_id') or task_id}",
        f"创建时间：{case.get('created_at', '')}",
        "",
        "一、事故概况",
        f"　　{case.get('input_text') or '（未填写文字描述）'}",
        "",
        "二、责任认定",
        f"　　当事人一：{_PARTY_LABEL.get(resp.get('party_1', 'unknown'), '待补充认定')}",
        f"　　当事人二：{_PARTY_LABEL.get(resp.get('party_2', 'unknown'), '待补充认定')}",
        f"　　责任比例：{resp.get('split') or '—'}",
        f"　　置信度：{judgment.get('confidence', 0.0):.2f}",
        "",
        "三、认定依据",
    ]
    basis = judgment.get("basis") or ["（无）"]
    lines += [f"　　{idx}. {item}" for idx, item in enumerate(basis, 1)]
    lines += ["", "四、认定理由"]
    reasoning = judgment.get("reasoning") or ["（无）"]
    lines += [f"　　{idx}. {item}" for idx, item in enumerate(reasoning, 1)]
    lines += ["", "五、应急与处置建议"]
    steps = response.get("steps") or []
    lines += [f"　　{step.get('order')}. {step.get('action')}" for step in steps] or ["　　（无）"]
    if response.get("insurance"):
        lines += ["", f"保险指引：{response['insurance']}"]
    lines += [
        "",
        "=" * 32,
        judgment.get("note", "本结果为智能辅助研判建议，非最终裁定，请以交管部门认定为准。"),
    ]
    text = "\n".join(lines)
    return PlainTextResponse(
        content=text,
        headers={"Content-Disposition": f'attachment; filename="draft-{task_id}.txt"'},
    )