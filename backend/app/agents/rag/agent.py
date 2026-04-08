from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...storage.config import MemoryConfig
from ...storage.manager import MemoryManager
from ...storage.storage import SearchResult

from ...knowledge.base import IngestResult, KnowledgeBase


class RAGAgent:
    """Knowledge ingestion and retrieval agent."""

    def __init__(self, config: Optional[MemoryConfig] = None, memory_manager: Optional[MemoryManager] = None):
        self.memory_manager = memory_manager or MemoryManager(config=config)
        self.knowledge_base = KnowledgeBase(self.memory_manager)

    def ingest(self, paths: List[str], user_id: Optional[str] = None, private: bool = False, recursive: bool = True) -> List[IngestResult]:
        return self.knowledge_base.ingest(paths=paths, user_id=user_id, private=private, recursive=recursive)

    def search(self, query: str, user_id: Optional[str] = None, limit: int = 5) -> List[SearchResult]:
        return self.knowledge_base.search(query=query, user_id=user_id, limit=limit)

    def stats(self) -> Dict[str, Any]:
        return self.memory_manager.get_stats()

