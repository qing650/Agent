from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from ...services.file_service import FileService
from ...services.runtime_service import get_runtime
from ...workflows.rag_flow import RagFlow
from ..schemas import ApiEnvelope, IndexDirectoryRequest

router = APIRouter()


def _build_flow() -> RagFlow:
    runtime = get_runtime()
    return RagFlow(FileService(runtime))


@router.post("/upload", response_model=ApiEnvelope)
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(default=None),
    private: bool = Form(default=False),
) -> ApiEnvelope:
    flow = _build_flow()
    return ApiEnvelope(data=await flow.upload_file(file=file, user_id=user_id, private=private))


@router.post("/index_directory", response_model=ApiEnvelope)
async def index_directory(request: IndexDirectoryRequest) -> ApiEnvelope:
    flow = _build_flow()
    return ApiEnvelope(
        data=flow.index_directory(
            directory_path=request.directory_path,
            user_id=request.user_id,
            private=request.private,
            recursive=request.recursive,
        )
    )


@router.get("/documents", response_model=ApiEnvelope)
async def list_documents() -> ApiEnvelope:
    flow = _build_flow()
    return ApiEnvelope(data=flow.list_documents())
