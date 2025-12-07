# app/models.py

from pydantic import BaseModel
from typing import List, Literal


class AnalyzeRequest(BaseModel):
    page_ids: List[str]
    top_k: int = 5
    model: Literal["gpt", "claude"] = "gpt"


class AnalyzeResponse(BaseModel):
    prompt: str
    context: List[str]
    analysis: str
