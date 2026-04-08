from __future__ import annotations

from fastapi import APIRouter

from ...services.runtime_service import get_runtime
from ..schemas import ApiEnvelope

router = APIRouter()


@router.get("/health", response_model=ApiEnvelope)
async def health_check() -> ApiEnvelope:
    runtime = get_runtime()
    return ApiEnvelope(data=runtime.health_snapshot())
