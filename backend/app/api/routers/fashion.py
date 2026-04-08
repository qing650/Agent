from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...services.fashion_service import FashionService
from ...services.runtime_service import get_runtime
from ...workflows.fashion_flow import FashionFlow
from ..schemas import ApiEnvelope, FashionAdviceRequest

router = APIRouter()


def _build_flow() -> FashionFlow:
    runtime = get_runtime()
    return FashionFlow(FashionService(runtime))


def _format_sse(payload: Dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/fashion/advice", response_model=ApiEnvelope)
async def fashion_advice(request: FashionAdviceRequest) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(
            data=flow.advise(
                city=request.city,
                occasion=request.occasion,
                style_preference=request.style_preference,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/fashion/advice_stream")
async def fashion_advice_stream(request: FashionAdviceRequest) -> StreamingResponse:
    flow = _build_flow()

    async def event_generator() -> AsyncIterator[str]:
        try:
            for event in flow.stream_advise(
                city=request.city,
                occasion=request.occasion,
                style_preference=request.style_preference,
            ):
                yield _format_sse(event)
        except Exception as exc:
            yield _format_sse({"type": "error", "data": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
