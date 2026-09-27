"""
共享数据模型（Pydantic），对应文档中定义的 JSON 契约：
- scene.json     (M1 视频感知输出结构)
- judgment.json  (M3 责任判定输出结构)
- response.json  (M4 应急方案输出结构)
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- 输入 ----------
class CaseInput(BaseModel):
    """案件输入：三种方式（视频 / 照片 / 文字描述）至少提供一种。"""
    video_id: Optional[str] = None
    # 结构化场景（若已由前端/感知生成）
    scene_id: Optional[str] = None
    # 文字描述（补录 / 兜底输入）
    text_description: Optional[str] = Field(default="", description="人工文字描述现场要素")


class TextSupplement(BaseModel):
    """文字补录的现场要素（感知降级时使用）。"""
    text: str = Field(..., description="对事故现场的自然语言描述")


# ---------- M1 感知输出 ----------
class TrajectoryPoint(BaseModel):
    t: float = Field(..., description="时间（秒）")
    x: float = Field(..., description="归一化横坐标 0-1")
    y: float = Field(..., description="归一化纵坐标 0-1")
    speed_kmh: float = 0.0


class Vehicle(BaseModel):
    id: int
    type: str = "car"  # car / truck / motorcycle / bicycle / pedestrian
    trajectory: list[TrajectoryPoint] = []
    max_speed_kmh: float = 0.0


class SceneEvent(BaseModel):
    time: float
    type: str = "collision"  # collision / near_miss / signal_change ...
    participants: list[int] = []
    keyframe: Optional[str] = None


class Scene(BaseModel):
    """scene.json —— M1 输出，M3/M4 消费。"""
    scene_id: str
    source: str = "mock"  # mock / video / text
    vehicles: list[Vehicle] = []
    events: list[SceneEvent] = []
    road: str = "urban_intersection"
    lane_markings: str = "dashed"
    traffic_light: str = "green"
    visibility: str = "day"
    confidence: float = 0.0  # 感知置信度


# ---------- M2 检索结果 ----------
class RetrievedDoc(BaseModel):
    id: str
    title: str
    content: str
    source: str = "law"  # law / case
    score: float = 0.0


# ---------- M3 判定输出 ----------
class Responsibility(BaseModel):
    party_1: str = "unknown"  # primary / secondary / equal / none / unknown
    party_2: str = "unknown"
    split: str = ""  # "70/30"


class Judgment(BaseModel):
    """judgment.json —— M3 输出。"""
    scene_id: str
    responsibility: Responsibility
    basis: list[str] = []
    reasoning: list[str] = []
    confidence: float = 0.0
    note: str = "本结果为智能辅助研判建议，非最终裁定，请以交管部门认定为准。"


# ---------- M4 应急输出 ----------
class ResponseStep(BaseModel):
    order: int
    action: str
    urgent: bool = False


class EmergencyResponse(BaseModel):
    """response.json —— M4 输出。"""
    scene_id: str
    accident_type: str = "general"
    priority: int = 1
    steps: list[ResponseStep] = []
    insurance: str = ""


# ---------- 汇聚输出（给前端） ----------
class AnalyzeResult(BaseModel):
    case_id: str
    scene: Optional[Scene] = None
    retrieved: list[RetrievedDoc] = []
    judgment: Optional[Judgment] = None
    response: Optional[EmergencyResponse] = None


# ---------- 任务状态 ----------
class TaskInfo(BaseModel):
    task_id: str
    status: str = "pending"  # pending / perceiving / retrieving / judging / responding / done / failed
    progress: float = 0.0
    error: Optional[str] = None
    result: Optional[AnalyzeResult] = None
