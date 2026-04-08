from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ...services.novel_service import NovelService
from ...services.runtime_service import get_runtime
from ...workflows.novel_flow import NovelFlow
from ..schemas import (
    ApiEnvelope,
    ChapterGenerateRequest,
    ChapterUpdateRequest,
    OutlineGenerateRequest,
    OutlineUpdateRequest,
)

router = APIRouter()


def _build_flow() -> NovelFlow:
    runtime = get_runtime()
    return NovelFlow(NovelService(runtime))


def _format_sse(payload: Dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/novel/projects", response_model=ApiEnvelope)
async def list_projects() -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(data={"projects": flow.list_projects()})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/novel/projects/{title}/{novel_id}", response_model=ApiEnvelope)
async def get_project(title: str, novel_id: str) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(data=flow.get_project(title=title, novel_id=novel_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/novel/outline/generate", response_model=ApiEnvelope)
async def generate_outline(request: OutlineGenerateRequest) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(
            data=flow.generate_outline(
                novel_id=request.novel_id,
                title=request.title,
                user_input=request.user_input,
                tags=request.tags,
                target_length=request.target_length,
                style_tags=request.style_tags,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/novel/outline/generate_stream")
async def generate_outline_stream(request: OutlineGenerateRequest) -> StreamingResponse:
    flow = _build_flow()

    async def event_generator() -> AsyncIterator[str]:
        try:
            for event in flow.stream_generate_outline(
                novel_id=request.novel_id,
                title=request.title,
                user_input=request.user_input,
                tags=request.tags,
                target_length=request.target_length,
                style_tags=request.style_tags,
            ):
                yield _format_sse(event)
        except Exception as exc:
            yield _format_sse({"type": "error", "data": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/novel/outline/{title}/{novel_id}/{note_id}", response_model=ApiEnvelope)
async def get_outline(title: str, novel_id: str, note_id: str) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(data=flow.get_outline(title=title, novel_id=novel_id, note_id=note_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/novel/outline/update", response_model=ApiEnvelope)
async def update_outline(request: OutlineUpdateRequest) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(
            data=flow.update_outline(
                title=request.title,
                novel_id=request.novel_id,
                note_id=request.note_id,
                content=request.content,
                tags=request.tags,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/novel/outline/{title}/{novel_id}/{note_id}", response_model=ApiEnvelope)
async def delete_outline(title: str, novel_id: str, note_id: str) -> ApiEnvelope:
    flow = _build_flow()
    try:
        payload = flow.delete_outline(title=title, novel_id=novel_id, note_id=note_id)
        return ApiEnvelope(code=200 if payload["deleted"] else 404, message="success" if payload["deleted"] else "not_found", data=payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/novel/chapter/generate", response_model=ApiEnvelope)
async def generate_chapters(request: ChapterGenerateRequest) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(
            data=flow.generate_chapters(
                novel_id=request.novel_id,
                title=request.title,
                user_input=request.user_input,
                num_chapters=request.num_chapters,
                chapter_length=request.chapter_length,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/novel/chapter/generate_stream")
async def generate_chapters_stream(request: ChapterGenerateRequest) -> StreamingResponse:
    flow = _build_flow()

    async def event_generator() -> AsyncIterator[str]:
        try:
            for event in flow.stream_generate_chapters(
                novel_id=request.novel_id,
                title=request.title,
                user_input=request.user_input,
                num_chapters=request.num_chapters,
                chapter_length=request.chapter_length,
            ):
                yield _format_sse(event)
        except Exception as exc:
            yield _format_sse({"type": "error", "data": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/novel/chapter/{title}/{novel_id}/{note_id}", response_model=ApiEnvelope)
async def get_chapter(title: str, novel_id: str, note_id: str) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(data=flow.get_chapter(title=title, novel_id=novel_id, note_id=note_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/novel/chapter/update", response_model=ApiEnvelope)
async def update_chapter(request: ChapterUpdateRequest) -> ApiEnvelope:
    flow = _build_flow()
    try:
        return ApiEnvelope(
            data=flow.update_chapter(
                title=request.title,
                novel_id=request.novel_id,
                note_id=request.note_id,
                content=request.content,
                chapter_title=request.chapter_title,
                summary=request.summary,
                next_chapter_prediction=request.next_chapter_prediction,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/novel/chapter/{title}/{novel_id}/{note_id}", response_model=ApiEnvelope)
async def delete_chapter(title: str, novel_id: str, note_id: str) -> ApiEnvelope:
    flow = _build_flow()
    try:
        payload = flow.delete_chapter(title=title, novel_id=novel_id, note_id=note_id)
        return ApiEnvelope(code=200 if payload["deleted"] else 404, message="success" if payload["deleted"] else "not_found", data=payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
