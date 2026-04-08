from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..storage.manager import MemoryManager
from ..storage.storage import SearchResult

from .documents import DocumentParser


@dataclass
class IngestResult:
    path: str
    status: str
    chunks: int = 0
    error: Optional[str] = None


class KnowledgeBase:
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager
        self.parser = DocumentParser()

    def ingest(self, paths: List[str], user_id: Optional[str] = None, private: bool = False, recursive: bool = True) -> List[IngestResult]:
        effective_user = user_id or self.memory_manager.config.default_user_id
        visibility = "user" if private else "shared"
        files = self.parser.discover_files(paths, recursive=recursive)
        results: List[IngestResult] = []
        for file_path in files:
            try:
                document = self.parser.parse(file_path)
                if not document.text.strip():
                    results.append(IngestResult(path=str(file_path), status="failed", error="No extractable text"))
                    continue
                chunk_count = self.memory_manager.index_document(
                    file_path=document.path,
                    text=document.text,
                    visibility=visibility,
                    user_id=effective_user if private else None,
                    metadata=document.metadata,
                )
                results.append(IngestResult(path=str(file_path), status="indexed", chunks=chunk_count))
            except Exception as exc:
                results.append(IngestResult(path=str(file_path), status="failed", error=str(exc)))
        return results

    def search(self, query: str, user_id: Optional[str] = None, limit: int = 5) -> List[SearchResult]:
        return self.memory_manager.search_knowledge(query=query, user_id=user_id, limit=limit)

    def list_documents(self) -> List[str]:
        return self.memory_manager.storage.list_sources("knowledge")

