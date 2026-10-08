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
    x: float = Field(..., description="归一化横坐标 0-1（框中心）")
    y: float = Field(..., description="归一化纵坐标 0-1（框中心）")
    # 框宽高（归一化 0-1）。视频轨迹点里带着它，前端/结果里才能画出
    # 每个采样时刻的识别框；mock/文字场景没有框，默认 0。
    w: float = 0.0
    h: float = 0.0
    speed_kmh: float = 0.0


class Vehicle(BaseModel):
    id: int
    type: str = "car"  # car / truck / motorcycle / bicycle / pedestrian
    trajectory: list[TrajectoryPoint] = []
    max_speed_kmh: float = 0.0


class EventBox(BaseModel):
    """碰撞事件发生时刻某个参与者的识别框（归一化中心 + 宽高）。

    事故车辆是谁、框在哪，事件本身就带着 —— 前端据此在关键帧上
    标注事故车辆，不用重新跑检测。
    """

    id: int
    type: str = "car"
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0


class SceneEvent(BaseModel):
    time: float
    type: str = "collision"  # collision / near_miss / signal_change ...
    participants: list[int] = []
    confidence: float = 0.0  # 事件置信度（感知层输出，事故门控消费）
    # 碰撞时刻双方的识别框（归一化），前端/关键帧标注消费
    boxes: list[EventBox] = []
    # 标注了事故车辆识别框的关键帧图片（可访问 URL 或落盘文件名，无标注时为空）
    keyframe: Optional[str] = None
    # 碰撞几何（追尾/侧碰/正碰…，由 algo/collision.py 算出）。
    # 早先没这个字段，scene_summary.describe_events 读 geometry 恒为空 ——
    # 视频里辛苦算出来的碰撞形态根本进不了判定 prompt。
    geometry: Optional[str] = None


class PhotoTarget(BaseModel):
    """现场照片里检出的一个目标（单帧检测，只有静态位置，没有运动学）。"""

    type: str = "car"  # car / truck / bus / motorcycle / bicycle / pedestrian
    confidence: float = 0.0
    # 归一化 bbox：x/y 为左上角，w/h 为宽高，取值 0-1
    bbox: list[float] = []


class PhotoEvidence(BaseModel):
    """一张随附现场照片的检测证据。

    照片是静态单帧，给不出速度/方向（`detect_events` 需要多点轨迹），
    所以它只作为"现场有什么"的补充证据进判定上下文，不参与事故门控。
    """

    name: str = ""  # 落盘用的存储名（非原图回显，仅用于追溯/去重）
    width: int = 0
    height: int = 0
    targets: list[PhotoTarget] = []
    traffic_light: str = "unknown"  # red / green / yellow / unknown
    # 检测失败、mock 模式或静态画面的局限说明，前端与 prompt 都要如实展示
    note: str = ""


class TrafficLight(BaseModel):
    """路口信号灯及其颜色（M1 输出）。

    同一路口不同方向的红绿灯同时存在，因此逐灯记录颜色，
    traffic_light 汇总字段在多色并存时取 "mixed"。
    """
    id: int
    state: str = "unknown"  # red / green / yellow / unknown
    x: float = 0.0
    y: float = 0.0


class TextFacts(BaseModel):
    """从用户补充文字里**按关键词**提取的结构化现场要素。

    存在的理由：视频/照片识别不出"信号灯归属"（同一路口多方向灯并存 → `mixed`）
    也认不出路口指示牌，而这些恰是判责的关键要素 —— 用户自己往往说得清清楚楚
    （"我直行是绿灯，对方闯红灯左转"）。这里把它抽成结构化字段，
    以「用户陈述」的身份进判定上下文，最终仍由 LLM 统一辅助输出结论。

    两条纪律：
    1. **不冒充检测结果**：这些字段是用户陈述，检测结果优先级更高（见 `services/llm.py` 规则）；
    2. **不做过度归因**：没写"我方/对方"的裸"红灯"不硬塞给某一方，只记进 `matched`。
    """

    raw: str = ""                          # 用户原话（截断，便于追溯）
    my_light: str = "unknown"              # 我方方向信号灯：red / green / yellow / unknown
    other_light: str = "unknown"           # 对方方向信号灯
    red_light_violation: str = "unknown"   # yes / no / unknown —— 用户是否指认闯红灯
    red_light_by: str = ""                 # self / other —— 指认的是谁闯的
    signs: list[str] = []                  # 提到的路口指示牌 / 标志 / 标线
    violations: list[str] = []             # 提到的其他过错关键词（压实线、逆行…）
    matched: list[str] = []                # 命中的原词，便于人工核对


class Scene(BaseModel):
    """scene.json —— M1 输出，M3/M4 消费。"""
    scene_id: str
    source: str = "mock"  # mock / video / photo / text / text_fallback
    vehicles: list[Vehicle] = []
    events: list[SceneEvent] = []
    road: str = "urban_intersection"
    lane_markings: str = "dashed"
    traffic_light: str = "green"  # red / green / yellow / mixed / unknown
    traffic_lights: list[TrafficLight] = []
    # 随附现场照片的单帧检测证据（没有照片时为空）
    photos: list[PhotoEvidence] = []
    # 从用户补充文字里提取的现场要素（信号灯归属/指示牌/过错关键词）
    text_facts: Optional[TextFacts] = None
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


class PartyRole(BaseModel):
    """事故当事方（LLM 归类输出）：角色 + 检测到的目标类型。"""
    role: str = ""  # 后车 / 前车 / 驾驶方 / 行人 等
    type: str = ""  # car / truck / pedestrian 等


class Judgment(BaseModel):
    """judgment.json —— M3 输出。"""
    scene_id: str
    accident_type: str = ""  # 事故类型（追尾/普通碰撞/单方撞击公共设施/非事故）
    parties: list[PartyRole] = []  # 事故双方分别是什么（角色+类型）
    red_light_violation: str = "unknown"  # 是否闯红灯：yes / no / unknown
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
    # 视频感知阶段产出的关键帧（标注了事故车辆识别框，/outputs/ 下的 URL）。
    # 感知完成即可用，不必等任务 done —— 对话框/前端据此实时反馈关键帧片段
    keyframes: list[str] = []
