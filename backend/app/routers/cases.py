from fastapi import APIRouter, HTTPException
from app.services.mock_data import build_mock_tracking_scene

router = APIRouter()


@router.get("/cases")
async def list_cases():
    return {"items": [{"id": "c_1", "title": "追尾示例案件", "created_at": "2026-09-27T08:00:00Z"}]}


@router.get("/case/{case_id}")
async def case_detail(case_id: str):
    scene = build_mock_tracking_scene()
    return {
        "case_id": case_id,
        "scene": scene.model_dump(),
        "keyframes": ["/keyframes/c_1_1.jpg", "/keyframes/c_1_2.jpg"],
    }


@router.get("/case/{case_id}/export")
async def export_draft(case_id: str):
    return {"case_id": case_id, "draft": "交通事故认定书（草稿）\n\n… 由 result 生成 …"}
