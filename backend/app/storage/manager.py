from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..knowledge.chunker import TextChunker
from .config import MemoryConfig
from .conversation import ConversationStore
from ..knowledge.embedding import EmbeddingProvider, create_embedding_provider
from .storage import MemoryChunk, MemoryStorage, SearchResult
from ..knowledge.summarizer import MemorySummarizer

logger = logging.getLogger(__name__)


class MemoryManager:
    """Unified entry point for knowledge chunks, long-term memory, and conversations."""

    def __init__(self, config: Optional[MemoryConfig] = None, embedding_provider: Optional[EmbeddingProvider] = None):
        self.config = config or MemoryConfig()
        self.chunker = TextChunker(
            max_chars=self.config.chunk_size,
            overlap_chars=self.config.chunk_overlap,
        )
        
        # 根据配置选择存储后端
        self.storage: Union[MemoryStorage, Any] = self._init_storage()
        self.conversations = ConversationStore(self.config.get_conversation_db_path())
        
        # Initialize embedding provider with graceful fallback
        if embedding_provider:
            self.embedding_provider = embedding_provider
        else:
            self.embedding_provider = self._init_embedding_provider()
        
        self.summarizer = MemorySummarizer()
        self.use_milvus = self.config.use_milvus and hasattr(self.storage, 'search_vector')

    def _init_storage(self) -> Union[MemoryStorage, Any]:
        """Initialize storage backend (SQLite or Milvus)."""
        if self.config.use_milvus:
            try:
                from .milvus import MilvusStorage
                logger.info(f"Initializing Milvus storage: {self.config.milvus_uri}")
                return MilvusStorage(
                    uri=self.config.milvus_uri,
                    db_name=self.config.milvus_db_name,
                    collection_name=self.config.milvus_collection_name,
                    vector_dim=self.config.embedding_dimensions,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Milvus, falling back to SQLite: {e}")
                self.config.use_milvus = False

        # 默认使用SQLite
        logger.info("Using SQLite storage backend")
        return MemoryStorage(self.config.get_knowledge_db_path())

    def _init_embedding_provider(self) -> EmbeddingProvider:
        """Initialize embedding provider with automatic fallback to hash-based embedding.
        
        This ensures compatibility when using APIs that don't support OpenAI embedding models,
        like Alibaba's DashScope with Qwen models.
        """
        import os
        
        # 检�?base_url 是否为非 OpenAI API
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or ""
        is_dashscope = "dashscope" in base_url.lower()
        is_non_openai = base_url and "openai" not in base_url.lower()
        
        # 如果使用�?OpenAI API 或配置为 hash，直接用本地 hash embedding
        if is_non_openai or self.config.embedding_provider.lower() == "hash":
            logger.info("Using local hash-based embedding (non-OpenAI API detected)")
            from ..knowledge.embedding import HashEmbeddingProvider
            return HashEmbeddingProvider(dimensions=self.config.embedding_dimensions)
        
        # 否则尝试�?OpenAI embedding，失败则降级
        try:
            provider = create_embedding_provider(
                provider=self.config.embedding_provider,
                model=self.config.embedding_model,
                dimensions=self.config.embedding_dimensions,
            )
            # Log when an OpenAI-compatible embedding client is available
            if hasattr(provider, 'client'):
                logger.info(f"Using OpenAI embedding model: {self.config.embedding_model}")
            return provider
        except Exception as e:
            logger.warning(f"Failed to initialize embedding provider: {e}. Falling back to hash-based embedding.")
            from ..knowledge.embedding import HashEmbeddingProvider
            return HashEmbeddingProvider(dimensions=self.config.embedding_dimensions)

    def sync_text(
        self,
        path: str,
        text: str,
        source: str,
        visibility: str = "shared",
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        mtime: Optional[int] = None,
    ) -> int:
        """Sync text to storage, creating chunks and embeddings."""
        content = (text or "").strip()
        if not content:
            self.storage.delete_by_path(path=path, source=source, user_id=user_id)
            return 0

        file_hash = self._compute_hash(content)
        existing_hash = self._get_file_hash(path=path, source=source, user_id=user_id)
        if existing_hash == file_hash:
            logger.debug(f"Content unchanged for {path}, skipping")
            return 0

        self.storage.delete_by_path(path=path, source=source, user_id=user_id)
        chunks = self.chunker.chunk_text(content, title=title, metadata=metadata)
        if not chunks:
            return 0

        # 批量生成embeddings
        embeddings = self.embedding_provider.embed_batch(chunk.text for chunk in chunks)
        save_chunks: List[MemoryChunk] = []
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = self._build_chunk_id(path, source, user_id, chunk.start_line, chunk.end_line)
            save_chunks.append(
                MemoryChunk(
                    id=chunk_id,
                    source=source,
                    visibility=visibility,
                    path=path,
                    text=chunk.text,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    user_id=user_id,
                    title=chunk.title or title,
                    embedding=embedding,
                    metadata=chunk.metadata,
                    hash=self._compute_hash(chunk.text),
                )
            )

        # 保存chunks
        self.storage.save_chunks_batch(save_chunks)
        
        # Update file metadata when the backend supports it
        if hasattr(self.storage, 'update_file_metadata'):
            self.storage.update_file_metadata(
                path=path,
                source=source,
                visibility=visibility,
                user_id=user_id,
                file_hash=file_hash,
                mtime=mtime or int(dt.datetime.now().timestamp()),
                size=len(content.encode("utf-8")),
                metadata=metadata,
            )

        logger.info(f"Synced {len(save_chunks)} chunks for {path}")
        return len(save_chunks)

    def index_document(
        self,
        file_path: Path,
        text: str,
        visibility: str = "shared",
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Index a document file."""
        relative_path = self._normalize_path(file_path)
        stat = file_path.stat() if file_path.exists() else None
        return self.sync_text(
            path=relative_path,
            text=text,
            source="knowledge",
            visibility=visibility,
            user_id=user_id,
            title=file_path.name,
            metadata=metadata,
            mtime=int(stat.st_mtime) if stat else None,
        )

    def add_memory(self, content: str, user_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        """Add memory entry."""
        effective_user = user_id or self.config.default_user_id
        memory_file = self.config.get_user_memory_file(effective_user)
        existing = memory_file.read_text(encoding="utf-8") if memory_file.exists() else "# Long Term Memory\n\n"
        entry = f"- {content.strip()}\n"
        if entry not in existing:
            existing += entry
            memory_file.write_text(existing, encoding="utf-8")
        return self.sync_text(
            path=self._normalize_path(memory_file),
            text=existing,
            source="memory",
            visibility="user",
            user_id=effective_user,
            title=f"{effective_user} memory",
            metadata=metadata,
            mtime=int(memory_file.stat().st_mtime),
        )

    def summarize_to_daily_memory(self, session_id: str, user_id: Optional[str] = None, max_messages: int = 10) -> str:
        """Summarize session to daily memory."""
        messages = self.conversations.load_recent_messages(session_id, limit=max_messages)
        summary = self.summarizer.extract_memories(messages)
        daily_file = self.config.get_daily_memory_file(user_id)
        today_header = f"# Daily Memory {dt.date.today().isoformat()}\n\n"
        if not daily_file.exists():
            daily_file.write_text(today_header, encoding="utf-8")
        payload = summary.summary.strip()
        if payload:
            existing_content = daily_file.read_text(encoding="utf-8")
            section = f"## Session {session_id}\n\n{payload}\n\n"
            if section not in existing_content:
                with daily_file.open("a", encoding="utf-8") as handle:
                    handle.write(section)
                self.sync_text(
                    path=self._normalize_path(daily_file),
                    text=daily_file.read_text(encoding="utf-8"),
                    source="memory",
                    visibility="user",
                    user_id=user_id or self.config.default_user_id,
                    title=daily_file.name,
                    mtime=int(daily_file.stat().st_mtime),
                )
        return payload

    def remember_from_conversation(self, session_id: str, user_id: Optional[str] = None, max_messages: int = 8) -> List[str]:
        """Extract and store memories from conversation."""
        messages = self.conversations.load_recent_messages(session_id, limit=max_messages)
        summary = self.summarizer.extract_memories(messages)
        remembered: List[str] = []
        for fact in summary.facts:
            self.add_memory(fact, user_id=user_id, metadata={"session_id": session_id})
            remembered.append(fact)
        return remembered

    def search(
        self,
        query: str,
        sources: List[str],
        user_id: Optional[str] = None,
        include_shared: bool = True,
        limit: Optional[int] = None,
    ) -> List[SearchResult]:
        """Search across all storage."""
        max_results = limit or self.config.max_results
        
        # 向量搜索
        vector_results = self.storage.search_vector(
            query_embedding=self.embedding_provider.embed(query),
            sources=sources,
            user_id=user_id,
            include_shared=include_shared,
            limit=max_results * 3,
        )
        
        # Keyword search complements vector search
        keyword_results = self.storage.search_keyword(
            query=query,
            sources=sources,
            user_id=user_id,
            include_shared=include_shared,
            limit=max_results * 3,
        )
        
        return self._merge_results(vector_results, keyword_results, max_results)

    def search_knowledge(self, query: str, user_id: Optional[str] = None, limit: Optional[int] = None) -> List[SearchResult]:
        """Search in knowledge base."""
        return self.search(query=query, sources=["knowledge"], user_id=user_id, include_shared=True, limit=limit)

    def search_memory(self, query: str, user_id: Optional[str] = None, limit: Optional[int] = None) -> List[SearchResult]:
        """Search in memory (user-specific)."""
        if not user_id:
            return []
        return self.search(query=query, sources=["memory"], user_id=user_id, include_shared=False, limit=limit)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append message to conversation."""
        self.conversations.append_message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata,
            user_id=user_id or self.config.default_user_id,
        )

    def load_recent_conversation(self, session_id: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Load recent conversation messages."""
        return self.conversations.load_recent_messages(session_id, limit=limit)

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get full session history."""
        return self.conversations.load_all_messages(session_id)

    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all sessions."""
        return self.conversations.list_sessions(user_id=user_id)

    def clear_session(self, session_id: str) -> bool:
        """Clear a session."""
        return self.conversations.delete_session(session_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        stats = {}
        
        if hasattr(self.storage, 'get_stats'):
            stats = self.storage.get_stats()
        
        stats.update({
            "workspace": str(self.config.get_workspace_root()),
            "backend": "milvus" if self.use_milvus else "sqlite",
            "embedding_provider": self.config.embedding_provider,
            "embedding_model": self.config.embedding_model,
        })
        
        if hasattr(self.storage, 'list_sources'):
            stats["documents"] = self.storage.list_sources("knowledge")
        
        return stats

    def close(self) -> None:
        """Close all connections."""
        try:
            if hasattr(self.storage, 'close'):
                self.storage.close()
        except Exception as e:
            logger.error(f"Error closing storage: {e}")
        
        try:
            self.conversations.close()
        except Exception as e:
            logger.error(f"Error closing conversations: {e}")

    def _merge_results(
        self,
        vector_results: List[SearchResult],
        keyword_results: List[SearchResult],
        max_results: int,
    ) -> List[SearchResult]:
        """Merge and rank search results from multiple methods."""
        merged: Dict[Tuple[str, int, int, Optional[str]], SearchResult] = {}

        def absorb(results: List[SearchResult], weight: float) -> None:
            for result in results:
                key = (result.path, result.start_line, result.end_line, result.user_id)
                if key not in merged:
                    merged[key] = result
                    merged[key].score *= weight
                else:
                    merged[key].score += result.score * weight

        absorb(vector_results, self.config.vector_weight)
        absorb(keyword_results, self.config.keyword_weight)

        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return [item for item in ranked if item.score >= self.config.min_score][:max_results]

    def _normalize_path(self, path: Path) -> str:
        """Normalize file path."""
        try:
            return str(path.resolve().relative_to(self.config.project_root.resolve()))
        except ValueError:
            return str(path.resolve())

    def _build_chunk_id(
        self,
        path: str,
        source: str,
        user_id: Optional[str],
        start_line: int,
        end_line: int,
    ) -> str:
        """Build unique chunk ID."""
        seed = f"{path}:{source}:{user_id or ''}:{start_line}:{end_line}"
        return self._compute_hash(seed)

    @staticmethod
    def _compute_hash(text: str) -> str:
        """Compute hash of text."""
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()

    def _get_file_hash(self, path: str, source: str, user_id: Optional[str] = None) -> Optional[str]:
        """Get stored file hash if available."""
        if hasattr(self.storage, 'get_file_hash'):
            return self.storage.get_file_hash(path, source, user_id)
        return None


