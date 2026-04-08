from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...services.chat_service import ChatService
from ...services.runtime_service import get_runtime
from ...workflows.chat_flow import ChatFlow
from ..schemas import ApiEnvelope, ChatRequest, ClearRequest

router = APIRouter()


def _build_flow() -> ChatFlow:
    runtime = get_runtime()
    return ChatFlow(ChatService(runtime))


def _format_sse(payload: Dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat", response_model=ApiEnvelope)
async def chat(request: ChatRequest) -> ApiEnvelope:
    flow = _build_flow()
    try:
        response = flow.chat(
            question=request.question,
            session_id=request.session_id,
            user_id=request.user_id,
            top_k=request.top_k,
        )
        return ApiEnvelope(data=flow.serialize_chat_response(response))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/chat_stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    flow = _build_flow()

    async def event_generator() -> AsyncIterator[str]:
        try:
            for event in flow.stream_chat(
                question=request.question,
                session_id=request.session_id,
                user_id=request.user_id,
                top_k=request.top_k,
            ):
                yield _format_sse(event)
        except Exception as exc:
            yield _format_sse({"type": "error", "data": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/chat/session/{session_id}", response_model=ApiEnvelope)
async def get_session(session_id: str) -> ApiEnvelope:
    flow = _build_flow()
    session = flow.get_session(session_id)
    if session is None:
        return ApiEnvelope(code=404, message="not_found", data={"session_id": session_id, "history": []})
    return ApiEnvelope(data=session)


@router.get("/chat/sessions", response_model=ApiEnvelope)
async def list_sessions(user_id: Optional[str] = None) -> ApiEnvelope:
    flow = _build_flow()
    return ApiEnvelope(data=flow.list_sessions(user_id=user_id))


@router.post("/chat/clear", response_model=ApiEnvelope)
async def clear_session(request: ClearRequest) -> ApiEnvelope:
    flow = _build_flow()
    success = flow.clear_session(request.session_id)
    return ApiEnvelope(
        code=200 if success else 404,
        message="success" if success else "not_found",
        data={"cleared": success, "session_id": request.session_id},
    )
