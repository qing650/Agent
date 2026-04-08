from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from .runtime_service import AppRuntime


class FashionService:
    """Application-facing orchestration for weather fashion advice."""

    def __init__(self, runtime: AppRuntime):
        self.runtime = runtime

    def advise(
        self,
        *,
        city: str,
        occasion: Optional[str] = None,
        style_preference: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = self.runtime.fashion_coordinator.advise(
            city=city,
            occasion=occasion,
            style_preference=style_preference,
        )
        return result.to_dict()

    def stream_advise(
        self,
        *,
        city: str,
        occasion: Optional[str] = None,
        style_preference: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        return self.runtime.fashion_coordinator.stream_advise(
            city=city,
            occasion=occasion,
            style_preference=style_preference,
        )
