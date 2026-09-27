from pydantic import BaseModel, Field
from typing import List


class Action(BaseModel):
    order: int
    action: str
    urgent: bool = False
    checked: bool = False


class ResponsePlan(BaseModel):
    emergency_level: str = Field(default="low", description="high/medium/low")
    level_label: str = ""
    urgent_actions: List[Action] = []
    steps: List[Action] = []
    insurance_note: str = ""
    confidence: float = 1.0
