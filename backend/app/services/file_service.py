from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, UploadFile

from .runtime_service import AppRuntime


class FileService:
    """File ingestion and document listing orchestration."""

    def __init__(self, runtime: AppRuntime):
        self.runtime = runtime

    async def upload_file(
        self,
        file: UploadFile,
        user_id: Optional[str] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File name is required")

        upload_dir = self.runtime.config.get_upload_dir()
        save_path = self._build_upload_path(upload_dir, file.filename)
        content = await file.read()
        save_path.write_bytes(content)
        await file.close()

        results = self.runtime.rag_agent.ingest(
            paths=[str(save_path)],
            user_id=user_id,
            private=private,
            recursive=False,
        )
        result = results[0] if results else None
        if result is None or result.status != "indexed":
            raise HTTPException(status_code=500, detail=result.error if result else "Index failed")

        return {
            "filename": save_path.name,
            "path": str(save_path),
            "size": len(content),
            "chunks": result.chunks,
            "private": private,
        }

    def index_directory(
        self,
        directory_path: str,
        user_id: Optional[str] = None,
        private: bool = False,
        recursive: bool = True,
    ) -> Dict[str, Any]:
        directory = Path(directory_path).expanduser()
        if not directory.exists():
            raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

        results = self.runtime.rag_agent.ingest(
            paths=[str(directory)],
            user_id=user_id,
            private=private,
            recursive=recursive,
        )
        return {
            "total": len(results),
            "indexed": [item.__dict__ for item in results if item.status == "indexed"],
            "failed": [item.__dict__ for item in results if item.status != "indexed"],
        }

    def list_documents(self):
        return self.runtime.workspace_snapshot()["documents"]

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        sanitized = filename.replace(" ", "_")
        for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
            sanitized = sanitized.replace(char, "_")
        return sanitized

    def _build_upload_path(self, upload_dir: Path, filename: str) -> Path:
        safe_name = self._sanitize_filename(filename)
        candidate = upload_dir / safe_name
        if not candidate.exists():
            return candidate

        suffix = "".join(candidate.suffixes)
        stem = candidate.name[: -len(suffix)] if suffix else candidate.name
        return upload_dir / f"{stem}_{secrets.token_hex(4)}{suffix}"
