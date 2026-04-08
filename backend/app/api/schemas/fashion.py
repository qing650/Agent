from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FashionAdviceRequest(BaseModel):
    city: str = Field(min_length=1, max_length=120)
    occasion: Optional[str] = Field(default=None, max_length=120)
    style_preference: Optional[str] = Field(default=None, max_length=120)
