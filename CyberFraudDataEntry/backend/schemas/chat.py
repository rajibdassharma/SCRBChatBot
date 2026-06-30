from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class ChatResponse(BaseModel):
    answer: str
    sql: str | None = None
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    latency_ms: int = 0
    # Up to 3 LLM-suggested follow-up questions. Empty when generation
    # failed, when the model declined, or when the answer was "no rows
    # found" (nothing to drill into).
    followups: list[str] = []
