from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from ..agents.chat.agent import ChatAgent
from ..agents.fashion import FashionAgent, FashionCoordinatorAgent, WeatherAgent
from ..agents.novel.agent import NovelAgent
from ..agents.rag.agent import RAGAgent
from ..core.llm import ChatLLM
from ..storage.config import MemoryConfig
from ..storage.manager import MemoryManager

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


load_dotenv(_project_root() / ".env")


class AppRuntime:
    def __init__(self):
        self.project_root = _project_root()
        self.config = MemoryConfig(project_root=self.project_root)
        self.memory_manager = MemoryManager(config=self.config)
        self.rag_agent = RAGAgent(config=self.config, memory_manager=self.memory_manager)
        self.llm = ChatLLM()
        logger.info("LLM initialized: available=%s, model=%s", self.llm.available, self.llm.model)
        self.chat_agent = ChatAgent(
            config=self.config,
            memory_manager=self.memory_manager,
            llm=self.llm,
        )
        self.weather_agent = WeatherAgent()
        self.fashion_agent = FashionAgent(config=self.config, llm=self.llm)
        self.fashion_coordinator = FashionCoordinatorAgent(
            weather_agent=self.weather_agent,
            fashion_agent=self.fashion_agent,
        )
        self.novel_agent = NovelAgent(config=self.config, llm=self.llm)

    def health_snapshot(self) -> Dict[str, Any]:
        stats = self.memory_manager.get_stats()
        return {
            "service": "MyAgent",
            "status": "healthy",
            "workspace": stats["workspace"],
            "indexed_files": stats["files"],
            "indexed_chunks": stats["chunks"],
            "documents": stats["documents"],
            "backend": stats.get("backend"),
            "embedding_provider": stats.get("embedding_provider"),
        }

    def workspace_snapshot(self) -> Dict[str, Any]:
        stats = self.memory_manager.get_stats()
        sessions = self.memory_manager.list_sessions()
        return {
            "workspace": stats["workspace"],
            "indexed_files": stats["files"],
            "indexed_chunks": stats["chunks"],
            "documents": stats["documents"],
            "sessions": len(sessions),
            "backend": stats.get("backend"),
            "embedding_provider": stats.get("embedding_provider"),
            "embedding_model": stats.get("embedding_model"),
        }


@lru_cache(maxsize=1)
def get_runtime() -> AppRuntime:
    return AppRuntime()
