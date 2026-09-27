from pydantic import BaseModel, Field

class Point2D(BaseModel):
    x: float
    y: float


class Resolution(BaseModel):
    width: int = 1920
    height: int = 1080


class Source(BaseModel):
    video_id: str = "v_mock"
    fps: int = 30
    duration_s: float = 12.5
    resolution: Resolution = Resolution()
