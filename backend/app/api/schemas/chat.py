from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default")
    user_id: Optional[str] = Field(default=None)
    top_k: int = Field(default=4, ge=1, le=10)


class ClearRequest(BaseModel):
    session_id: str
