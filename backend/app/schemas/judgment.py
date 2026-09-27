from pydantic import BaseModel, Field
from typing import List, Optional


class Party(BaseModel):
    object_id: str
    role: str = "A"
    liability_pct: int = 0
    main_reason: str = ""


class Verdict(BaseModel):
    parties: List[Party] = []


class Law(BaseModel):
    article: str
    summary: str = ""


class Judgment(BaseModel):
    case_type: Optional[str] = None
    verdict: Verdict = Verdict()
    reasoning: List[str] = []
    laws: List[Law] = []
    confidence: float = 1.0
    low_confidence: bool = False
    needs_human_review: bool = False
    summary_text: str = ""
