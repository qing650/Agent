from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiEnvelope(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None
