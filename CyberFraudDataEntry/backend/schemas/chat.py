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
