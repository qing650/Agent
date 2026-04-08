from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .config import MemoryConfig


class MemoryService:
    """Simple file-oriented access to persisted long-term memories."""

    def __init__(self, config: MemoryConfig):
        self.config = config

    def list_files(self, user_id: Optional[str] = None) -> List[str]:
        root = self.config.get_user_memory_dir(user_id)
        return sorted(str(path.relative_to(root)) for path in root.glob("*.md"))

    def read_file(self, name: str, user_id: Optional[str] = None) -> str:
        path = self.config.get_user_memory_dir(user_id) / name
        if not path.exists():
            raise FileNotFoundError(name)
        return path.read_text(encoding="utf-8")

    def resolve(self, name: str, user_id: Optional[str] = None) -> Path:
        return self.config.get_user_memory_dir(user_id) / name
