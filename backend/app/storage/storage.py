from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MemoryChunk:
    id: str
    source: str
    visibility: str
    path: str
    text: str
    start_line: int
    end_line: int
    user_id: Optional[str] = None
    title: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    hash: str = ""


@dataclass
class SearchResult:
    path: str
    source: str
    visibility: str
    score: float
    snippet: str
    start_line: int
    end_line: int
    user_id: Optional[str] = None
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    content: str = ""

    @property
    def citation(self) -> str:
        suffix = f":{self.start_line}" if self.start_line else ""
        if self.end_line and self.end_line != self.start_line:
            suffix = f":{self.start_line}-{self.end_line}"
        return f"{self.path}{suffix}"

    def to_dict(self, include_content: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "path": self.path,
            "source": self.source,
            "visibility": self.visibility,
            "score": self.score,
            "snippet": self.snippet,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "user_id": self.user_id,
            "title": self.title,
            "metadata": self.metadata,
            "citation": self.citation,
        }
        if include_content:
            payload["content"] = self.content
        return payload


class MemoryStorage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.fts5_available = self._check_fts5()
        self._init_db()

    def _check_fts5(self) -> bool:
        try:
            self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts_probe USING fts5(content)")
            self.conn.execute("DROP TABLE __fts_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def _init_db(self) -> None:
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                visibility TEXT NOT NULL,
                path TEXT NOT NULL,
                text TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                user_id TEXT,
                title TEXT,
                embedding TEXT,
                metadata TEXT,
                hash TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT NOT NULL,
                source TEXT NOT NULL,
                visibility TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                hash TEXT NOT NULL,
                mtime INTEGER NOT NULL,
                size INTEGER NOT NULL,
                metadata TEXT,
                PRIMARY KEY (path, source, user_id)
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_visibility ON chunks(visibility)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_user_id ON chunks(user_id)")
        if self.fts5_available:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    text,
                    id UNINDEXED,
                    content='chunks',
                    content_rowid='rowid'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, text, id) VALUES (new.rowid, new.text, new.id);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, text, id) VALUES('delete', old.rowid, old.text, old.id);
                END
                """
            )
            self.conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, text, id) VALUES('delete', old.rowid, old.text, old.id);
                    INSERT INTO chunks_fts(rowid, text, id) VALUES (new.rowid, new.text, new.id);
                END
                """
            )
        self.conn.commit()

    def save_chunks_batch(self, chunks: List[MemoryChunk]) -> None:
        now = int(time.time())
        rows = [
            (
                chunk.id,
                chunk.source,
                chunk.visibility,
                chunk.path,
                chunk.text,
                chunk.start_line,
                chunk.end_line,
                chunk.user_id,
                chunk.title,
                json.dumps(chunk.embedding) if chunk.embedding is not None else None,
                json.dumps(chunk.metadata, ensure_ascii=False),
                chunk.hash or self.compute_hash(chunk.text),
                now,
            )
            for chunk in chunks
        ]
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO chunks (
                id, source, visibility, path, text, start_line, end_line,
                user_id, title, embedding, metadata, hash, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()

    def delete_by_path(self, path: str, source: Optional[str] = None, user_id: Optional[str] = None) -> None:
        query = "DELETE FROM chunks WHERE path = ?"
        params: List[Any] = [path]
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        else:
            query += " AND user_id IS NULL"
        self.conn.execute(query, params)
        file_query = "DELETE FROM files WHERE path = ?"
        file_params: List[Any] = [path]
        if source is not None:
            file_query += " AND source = ?"
            file_params.append(source)
        if user_id is not None:
            file_query += " AND user_id = ?"
            file_params.append(user_id)
        else:
            file_query += " AND user_id = ?"
            file_params.append("")
        self.conn.execute(file_query, file_params)
        self.conn.commit()

    def update_file_metadata(
        self,
        path: str,
        source: str,
        visibility: str,
        user_id: Optional[str],
        file_hash: str,
        mtime: int,
        size: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        normalized_user_id = user_id or ""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO files(path, source, visibility, user_id, hash, mtime, size, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                path,
                source,
                visibility,
                normalized_user_id,
                file_hash,
                mtime,
                size,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def get_file_hash(self, path: str, source: str, user_id: Optional[str] = None) -> Optional[str]:
        normalized_user_id = user_id or ""
        row = self.conn.execute(
            "SELECT hash FROM files WHERE path = ? AND source = ? AND user_id = ?",
            (path, source, normalized_user_id),
        ).fetchone()
        return None if row is None else str(row["hash"])

    def search_vector(
        self,
        query_embedding: List[float],
        sources: List[str],
        user_id: Optional[str],
        include_shared: bool,
        limit: int,
    ) -> List[SearchResult]:
        rows = self._select_candidate_rows(sources=sources, user_id=user_id, include_shared=include_shared, limit=0)
        results: List[SearchResult] = []
        for row in rows:
            if not row["embedding"]:
                continue
            embedding = json.loads(row["embedding"])
            score = self._cosine_similarity(query_embedding, embedding)
            if score <= 0:
                continue
            results.append(self._row_to_result(row, score))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def search_keyword(
        self,
        query: str,
        sources: List[str],
        user_id: Optional[str],
        include_shared: bool,
        limit: int,
    ) -> List[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []

        if self.fts5_available and self._is_fts_friendly(query):
            placeholders = ",".join("?" for _ in sources)
            sql = f"""
                SELECT c.*
                FROM chunks_fts f
                JOIN chunks c ON c.rowid = f.rowid
                WHERE f.text MATCH ?
                  AND c.source IN ({placeholders})
            """
            params: List[Any] = [self._to_fts_query(query), *sources]
            if user_id and include_shared:
                sql += " AND (c.visibility = 'shared' OR c.user_id = ?)"
                params.append(user_id)
            elif user_id:
                sql += " AND c.user_id = ?"
                params.append(user_id)
            elif include_shared:
                sql += " AND c.visibility = 'shared'"
            sql += " LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()
            return [self._row_to_result(row, self._keyword_score(query, row["text"])) for row in rows]

        rows = self._select_candidate_rows(sources=sources, user_id=user_id, include_shared=include_shared, limit=0)
        scored: List[SearchResult] = []
        for row in rows:
            score = self._keyword_score(query, row["text"])
            if score <= 0:
                continue
            scored.append(self._row_to_result(row, score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def get_stats(self) -> Dict[str, int]:
        chunk_count = self.conn.execute("SELECT COUNT(*) AS value FROM chunks").fetchone()["value"]
        file_count = self.conn.execute("SELECT COUNT(*) AS value FROM files").fetchone()["value"]
        return {"chunks": int(chunk_count), "files": int(file_count)}

    def list_sources(self, source: str) -> List[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT path FROM files WHERE source = ? ORDER BY path ASC",
            (source,),
        ).fetchall()
        return [str(row["path"]) for row in rows]

    def close(self) -> None:
        self.conn.close()

    def _select_candidate_rows(
        self,
        sources: List[str],
        user_id: Optional[str],
        include_shared: bool,
        limit: int,
    ) -> List[sqlite3.Row]:
        placeholders = ",".join("?" for _ in sources)
        sql = f"SELECT * FROM chunks WHERE source IN ({placeholders})"
        params: List[Any] = list(sources)
        if user_id and include_shared:
            sql += " AND (visibility = 'shared' OR user_id = ?)"
            params.append(user_id)
        elif user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        elif include_shared:
            sql += " AND visibility = 'shared'"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return self.conn.execute(sql, params).fetchall()

    def _row_to_result(self, row: sqlite3.Row, score: float) -> SearchResult:
        content = str(row["text"] or "").strip()
        snippet = content
        if len(snippet) > 300:
            snippet = f"{snippet[:297]}..."
        metadata = json.loads(row["metadata"] or "{}")
        return SearchResult(
            path=str(row["path"]),
            source=str(row["source"]),
            visibility=str(row["visibility"]),
            score=float(score),
            snippet=snippet,
            start_line=int(row["start_line"]),
            end_line=int(row["end_line"]),
            user_id=row["user_id"],
            title=row["title"],
            metadata=metadata,
            content=content,
        )

    def _keyword_score(self, query: str, text: str) -> float:
        query_tokens = self._tokenize(query)
        haystack = (text or "").lower()
        if not query_tokens or not haystack:
            return 0.0
        hits = sum(haystack.count(token) for token in query_tokens)
        if hits == 0:
            return 0.0
        coverage = len({token for token in query_tokens if token in haystack}) / len(query_tokens)
        density = min(1.0, hits / max(8, len(haystack) / 80))
        return round((coverage * 0.7) + (density * 0.3), 4)

    def _tokenize(self, text: str) -> List[str]:
        import re

        return re.findall(r"[\u4e00-\u9fff]|[a-z0-9_]+", (text or "").lower())

    def _is_fts_friendly(self, query: str) -> bool:
        return all(ord(char) < 128 for char in query)

    def _to_fts_query(self, query: str) -> str:
        return " ".join(self._tokenize(query))

    def _cosine_similarity(self, left: List[float], right: List[float]) -> float:
        size = min(len(left), len(right))
        if size == 0:
            return 0.0
        dot = sum(left[i] * right[i] for i in range(size))
        left_norm = math.sqrt(sum(value * value for value in left[:size])) or 1.0
        right_norm = math.sqrt(sum(value * value for value in right[:size])) or 1.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()
