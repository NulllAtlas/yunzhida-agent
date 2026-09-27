from pydantic import BaseModel, Field
from typing import List, Optional
from .common import Source, Point2D


class TrackPoint(BaseModel):
    t: float
    x: float
    y: float
    w: float
    h: float
    speed: float = 0.0
    heading: float = 0.0


class SceneObject(BaseModel):
    id: str
    kind: str = Field(default="vehicle", description="vehicle/pedestrian/non_motor/other")
    category: str = "car"
    trajectory: List[TrackPoint] = []
    keyframes: List[float] = []
    confidence: float = 1.0


class SceneEvent(BaseModel):
    type: str
    t: float
    objects: List[str] = []
    impact_speed: Optional[float] = None
    confidence: float = 1.0


class TrafficLight(BaseModel):
    present: bool = False
    state: Optional[str] = None


class SceneFactors(BaseModel):
    lighting: str = "day"
    weather: str = "clear"
    road_type: str = "road"
    traffic_light: TrafficLight = TrafficLight()
    lanes_detected: bool = False
    night: bool = False
    occlusion: bool = False


class Scene(BaseModel):
    scene_id: str = "s_mock"
    source: Source = Source()
    objects: List[SceneObject] = []
    events: List[SceneEvent] = []
    scene_factors: SceneFactors = SceneFactors()
    confidence: float = 1.0
    low_confidence: bool = False
    notes: List[str] = []
    schema_version: str = "1.0"
