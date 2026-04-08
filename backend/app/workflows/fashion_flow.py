from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from ..services.fashion_service import FashionService


class FashionFlow:
    """Thin workflow wrapper around the fashion service."""

    def __init__(self, service: FashionService):
        self.service = service

    def advise(
        self,
        *,
        city: str,
        occasion: Optional[str] = None,
        style_preference: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.service.advise(
            city=city,
            occasion=occasion,
            style_preference=style_preference,
        )

    def stream_advise(
        self,
        *,
        city: str,
        occasion: Optional[str] = None,
        style_preference: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        return self.service.stream_advise(
            city=city,
            occasion=occasion,
            style_preference=style_preference,
        )
