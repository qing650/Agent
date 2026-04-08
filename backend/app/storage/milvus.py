"""Milvus vector database integration for efficient retrieval."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .storage import MemoryChunk, SearchResult

logger = logging.getLogger(__name__)


class MilvusStorage:
    """Milvus vector database storage for memory chunks."""

    def __init__(
        self,
        uri: str = "http://localhost:19530",
        db_name: str = "myagent",
        collection_name: str = "chunks",
        vector_dim: int = 384,
    ):
        """Initialize Milvus storage.
        
        Args:
            uri: Milvus server URI (e.g., 'http://localhost:19530' or 'milvus://localhost')
            db_name: Database name
            collection_name: Collection name for storing chunks
            vector_dim: Dimension of embedding vectors
        """
        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections
        except ImportError:
            raise ImportError("pymilvus is required. Install with: pip install pymilvus")

        self.uri = uri
        self.db_name = db_name
        self.collection_name = collection_name
        self.vector_dim = vector_dim
        self._collection: Optional[Collection] = None
        self._connected = False

        # 连接到Milvus
        try:
            connections.connect(
                alias="default",
                uri=uri,
            )
            self._connected = True
            logger.info(f"Connected to Milvus at {uri}")

            # 使用或创建数据库
            try:
                from pymilvus import db
                db.create_db(db_name=db_name)
            except Exception as e:
                logger.debug(f"Database creation/connection: {e}")

            # 初始化集合
            self._init_collection()
        except Exception as e:
            logger.error(f"Failed to initialize Milvus: {e}")
            raise

    def _init_collection(self) -> None:
        """Initialize or get Milvus collection."""
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections

        try:
            # 检查集合是否存在
            if self.collection_name in connections.list_collections(using="default"):
                logger.info(f"Using existing collection: {self.collection_name}")
                self._collection = Collection(
                    name=self.collection_name,
                    using="default",
                )
            else:
                # 创建新集合
                fields = [
                    FieldSchema(
                        name="id",
                        dtype=DataType.VARCHAR,
                        max_length=256,
                        is_primary=True,
                    ),
                    FieldSchema(
                        name="source",
                        dtype=DataType.VARCHAR,
                        max_length=50,
                    ),
                    FieldSchema(
                        name="visibility",
                        dtype=DataType.VARCHAR,
                        max_length=20,
                    ),
                    FieldSchema(
                        name="path",
                        dtype=DataType.VARCHAR,
                        max_length=512,
                    ),
                    FieldSchema(
                        name="text",
                        dtype=DataType.VARCHAR,
                        max_length=65535,
                    ),
                    FieldSchema(
                        name="start_line",
                        dtype=DataType.INT64,
                    ),
                    FieldSchema(
                        name="end_line",
                        dtype=DataType.INT64,
                    ),
                    FieldSchema(
                        name="user_id",
                        dtype=DataType.VARCHAR,
                        max_length=128,
                    ),
                    FieldSchema(
                        name="title",
                        dtype=DataType.VARCHAR,
                        max_length=256,
                    ),
                    FieldSchema(
                        name="embedding",
                        dtype=DataType.FLOAT_VECTOR,
                        dim=self.vector_dim,
                    ),
                    FieldSchema(
                        name="metadata",
                        dtype=DataType.VARCHAR,
                        max_length=65535,
                    ),
                    FieldSchema(
                        name="hash",
                        dtype=DataType.VARCHAR,
                        max_length=64,
                    ),
                    FieldSchema(
                        name="updated_at",
                        dtype=DataType.INT64,
                    ),
                ]

                schema = CollectionSchema(
                    fields=fields,
                    description="Memory chunks storage",
                )

                self._collection = Collection(
                    name=self.collection_name,
                    schema=schema,
                    using="default",
                )

                # 创建索引
                self._collection.create_index(
                    field_name="embedding",
                    index_params={
                        "index_type": "IVF_FLAT",
                        "metric_type": "L2",
                        "params": {"nlist": 128},
                    },
                )

                # 创建标量索引用于过滤
                for field in ["source", "visibility", "user_id", "path"]:
                    try:
                        self._collection.create_index(
                            field_name=field,
                            index_params={"index_type": "INVERTED"},
                        )
                    except Exception as e:
                        logger.debug(f"Failed to create index on {field}: {e}")

                logger.info(f"Created new collection: {self.collection_name}")

            # 加载集合到内存
            self._collection.load()
            logger.info("Collection loaded to memory")

        except Exception as e:
            logger.error(f"Collection initialization failed: {e}")
            raise

    def save_chunks_batch(self, chunks: List[MemoryChunk]) -> None:
        """Save multiple chunks to Milvus.
        
        Args:
            chunks: List of MemoryChunk objects
        """
        if not chunks or not self._collection:
            return

        try:
            # 准备数据
            data = {
                "id": [chunk.id for chunk in chunks],
                "source": [chunk.source for chunk in chunks],
                "visibility": [chunk.visibility for chunk in chunks],
                "path": [chunk.path for chunk in chunks],
                "text": [chunk.text for chunk in chunks],
                "start_line": [chunk.start_line for chunk in chunks],
                "end_line": [chunk.end_line for chunk in chunks],
                "user_id": [chunk.user_id or "" for chunk in chunks],
                "title": [chunk.title or "" for chunk in chunks],
                "embedding": [chunk.embedding or [0.0] * self.vector_dim for chunk in chunks],
                "metadata": [json.dumps(chunk.metadata) for chunk in chunks],
                "hash": [chunk.hash for chunk in chunks],
                "updated_at": [int(__import__("time").time() * 1000) for _ in chunks],
            }

            result = self._collection.insert(data)
            logger.info(f"Inserted {len(chunks)} chunks, IDs: {result.primary_keys[:3]}...")

            # 刷新以确保数据可搜索
            self._collection.flush()

        except Exception as e:
            logger.error(f"Failed to save chunks: {e}")
            raise

    def search_vector(
        self,
        query_embedding: List[float],
        sources: List[str],
        user_id: Optional[str] = None,
        include_shared: bool = True,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Search using vector similarity.
        
        Args:
            query_embedding: Query embedding vector
            sources: List of sources to search in
            user_id: User ID for filtering
            include_shared: Include shared (non-user-specific) results
            limit: Maximum results to return
            
        Returns:
            List of SearchResult objects
        """
        if not self._collection:
            return []

        try:
            # 构建过滤条件
            filters = self._build_filter(sources, user_id, include_shared)

            # 执行向量搜索
            search_params = {
                "metric_type": "L2",
                "params": {"nprobe": 10},
            }

            results = self._collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=limit,
                expr=filters,
                output_fields=[
                    "id",
                    "source",
                    "visibility",
                    "path",
                    "text",
                    "start_line",
                    "end_line",
                    "user_id",
                    "title",
                    "metadata",
                ],
            )

            search_results: List[SearchResult] = []
            for hits in results:
                for hit in hits:
                    metadata = json.loads(hit.entity.metadata) if hit.entity.metadata else {}
                    # L2距离转换为相似度分数（0-1）
                    distance = hit.distance
                    score = max(0.0, 1.0 - distance / 2.0)

                    search_results.append(
                        SearchResult(
                            path=hit.entity.path,
                            source=hit.entity.source,
                            visibility=hit.entity.visibility,
                            score=score,
                            snippet=hit.entity.text,
                            start_line=hit.entity.start_line,
                            end_line=hit.entity.end_line,
                            user_id=hit.entity.user_id or None,
                            title=hit.entity.title,
                            metadata=metadata,
                            content=hit.entity.text,
                        )
                    )

            return search_results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def search_keyword(
        self,
        query: str,
        sources: List[str],
        user_id: Optional[str] = None,
        include_shared: bool = True,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Search using keyword matching on text field.
        
        Args:
            query: Search query text
            sources: List of sources to search in
            user_id: User ID for filtering
            include_shared: Include shared results
            limit: Maximum results to return
            
        Returns:
            List of SearchResult objects
        """
        if not self._collection:
            return []

        try:
            # Milvus不原生支持全文搜索，使用标量过滤+返回所有结果
            # 然后在Python端进行keyword匹配
            filters = self._build_filter(sources, user_id, include_shared)

            # 获取所有符合过滤条件的文档
            results = self._collection.query(
                expr=filters,
                output_fields=[
                    "id",
                    "source",
                    "visibility",
                    "path",
                    "text",
                    "start_line",
                    "end_line",
                    "user_id",
                    "title",
                    "metadata",
                ],
                limit=limit * 3,  # 获取更多然后过滤
            )

            # Python端进行关键词匹配和评分
            keywords = query.lower().split()
            scored_results: List[Tuple[SearchResult, float]] = []

            for doc in results:
                text_lower = doc["text"].lower()
                score = 0.0

                # 计算关键词匹配分数
                for keyword in keywords:
                    if keyword in text_lower:
                        score += 1.0 / len(keywords)

                if score > 0:
                    metadata = json.loads(doc.get("metadata", "{}")) if doc.get("metadata") else {}
                    scored_results.append(
                        (
                            SearchResult(
                                path=doc["path"],
                                source=doc["source"],
                                visibility=doc["visibility"],
                                score=min(1.0, score),
                                snippet=doc["text"],
                                start_line=doc["start_line"],
                                end_line=doc["end_line"],
                                user_id=doc.get("user_id") or None,
                                title=doc.get("title"),
                                metadata=metadata,
                                content=doc["text"],
                            ),
                            score,
                        )
                    )

            # 按分数排序
            scored_results.sort(key=lambda x: x[1], reverse=True)
            return [result for result, _ in scored_results[:limit]]

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    def delete_by_path(
        self,
        path: str,
        source: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Delete chunks by path and source.
        
        Args:
            path: File path
            source: Source type
            user_id: User ID (optional)
        """
        if not self._collection:
            return

        try:
            expr = f'path == "{path}" && source == "{source}"'
            if user_id:
                expr += f' && user_id == "{user_id}"'
            else:
                expr += ' && user_id == ""'

            self._collection.delete(expr=expr)
            logger.info(f"Deleted chunks: path={path}, source={source}")

        except Exception as e:
            logger.error(f"Failed to delete chunks: {e}")

    def close(self) -> None:
        """Close connection to Milvus."""
        try:
            if self._collection:
                self._collection.release()
            if self._connected:
                from pymilvus import connections
                connections.disconnect(alias="default")
            logger.info("Milvus connection closed")
        except Exception as e:
            logger.error(f"Error closing Milvus connection: {e}")

    @staticmethod
    def _build_filter(sources: List[str], user_id: Optional[str], include_shared: bool) -> str:
        """Build Milvus filter expression."""
        filters: List[str] = []

        # 源过滤
        if sources:
            source_expr = " || ".join(f'source == "{s}"' for s in sources)
            filters.append(f"({source_expr})")

        # 用户/可见性过滤
        if user_id and not include_shared:
            filters.append(f'(user_id == "{user_id}" || user_id == "")')
        elif include_shared:
            filters.append(f'(user_id == "{user_id}" || user_id == "" || visibility == "shared")')

        if not filters:
            return ""

        return " && ".join(filters)
