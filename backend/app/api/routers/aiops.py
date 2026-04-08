from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...services.runtime_service import get_runtime

router = APIRouter()


def _format_sse(payload: dict) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/aiops")
async def workspace_diagnosis() -> StreamingResponse:
    runtime = get_runtime()
    snapshot = runtime.workspace_snapshot()

    async def event_generator() -> AsyncIterator[str]:
        messages = [
            {"type": "status", "data": "Scanning workspace status..."},
            {"type": "status", "data": f"Indexed files: {snapshot['indexed_files']}"},
            {"type": "status", "data": f"Indexed chunks: {snapshot['indexed_chunks']}"},
            {"type": "status", "data": f"Conversation sessions: {snapshot['sessions']}"},
            {"type": "report", "data": "\n".join(f"- {item}" for item in snapshot["documents"][:20]) or "No indexed documents."},
            {"type": "done", "data": snapshot},
        ]
        for message in messages:
            yield _format_sse(message)
            await asyncio.sleep(0.05)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
