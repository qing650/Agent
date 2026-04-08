from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass
class MemoryConfig:
    """Runtime configuration for knowledge, memory, and conversation state."""

    project_root: Path = field(default_factory=_project_root)
    workspace_name: str = "workspace"
    knowledge_db_name: str = "knowledge.db"
    conversation_db_name: str = "conversations.db"
    memory_folder_name: str = "memories"
    chunk_size: int = 900
    chunk_overlap: int = 150
    max_results: int = 6
    min_score: float = 0.1
    vector_weight: float = 0.55
    keyword_weight: float = 0.45
    search_candidate_multiplier: int = 3
    knowledge_search_limit: int = 6
    memory_search_limit: int = 4
    knowledge_context_limit: int = 4
    memory_context_limit: int = 2
    history_message_limit: int = 8
    max_history_chars: int = 2400
    max_context_chars: int = 3200
    default_user_id: str = "default"
    embedding_provider: str = field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "auto"))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    embedding_dimensions: int = 256

    # Milvus配置
    use_milvus: bool = field(default_factory=lambda: os.getenv("USE_MILVUS", "false").lower() in ("true", "1", "yes"))
    milvus_uri: str = field(default_factory=lambda: os.getenv("MILVUS_URI", "http://localhost:19530"))
    milvus_db_name: str = field(default_factory=lambda: os.getenv("MILVUS_DB_NAME", "myagent"))
    milvus_collection_name: str = field(default_factory=lambda: os.getenv("MILVUS_COLLECTION_NAME", "chunks"))

    def get_workspace_root(self) -> Path:
        path = self.project_root / self.workspace_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_data_dir(self) -> Path:
        path = self.get_workspace_root() / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_upload_dir(self) -> Path:
        path = self.get_workspace_root() / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_memory_root(self) -> Path:
        path = self.get_workspace_root() / self.memory_folder_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_knowledge_db_path(self) -> Path:
        return self.get_data_dir() / self.knowledge_db_name

    def get_conversation_db_path(self) -> Path:
        return self.get_data_dir() / self.conversation_db_name

    def get_user_memory_dir(self, user_id: Optional[str] = None) -> Path:
        effective_user = user_id or self.default_user_id
        path = self.get_memory_root() / "users" / effective_user
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_user_memory_file(self, user_id: Optional[str] = None) -> Path:
        return self.get_user_memory_dir(user_id) / "MEMORY.md"

    def get_daily_memory_file(self, user_id: Optional[str] = None, day: Optional[str] = None) -> Path:
        import datetime as _dt

        effective_day = day or _dt.date.today().isoformat()
        return self.get_user_memory_dir(user_id) / f"{effective_day}.md"

