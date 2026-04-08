from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import UploadFile

from ..services.file_service import FileService


class RagFlow:
    """Thin workflow wrapper around file/RAG service."""

    def __init__(self, service: FileService):
        self.service = service

    async def upload_file(
        self,
        file: UploadFile,
        user_id: Optional[str] = None,
        private: bool = False,
    ) -> Dict[str, Any]:
        return await self.service.upload_file(file=file, user_id=user_id, private=private)

    def index_directory(
        self,
        directory_path: str,
        user_id: Optional[str] = None,
        private: bool = False,
        recursive: bool = True,
    ) -> Dict[str, Any]:
        return self.service.index_directory(
            directory_path=directory_path,
            user_id=user_id,
            private=private,
            recursive=recursive,
        )

    def list_documents(self):
        return self.service.list_documents()
