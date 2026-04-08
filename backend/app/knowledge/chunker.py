from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TextChunk:
    text: str
    start_line: int
    end_line: int
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TextChunker:
    """Chunk text while preserving loose paragraph and heading structure."""

    def __init__(self, max_chars: int = 3600, overlap_chars: int = 600):
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk_text(self, text: str, title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> List[TextChunk]:
        clean_text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not clean_text:
            return []

        metadata = dict(metadata or {})
        lines = clean_text.split("\n")
        chunks: List[TextChunk] = []
        current_lines: List[str] = []
        current_start = 1
        current_len = 0
        active_heading = title

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip()
            if line.lstrip().startswith("#"):
                active_heading = line.lstrip("#").strip() or active_heading

            line_len = len(line) + 1
            if line_len > self.max_chars:
                if current_lines:
                    chunks.append(
                        self._build_chunk(
                            current_lines,
                            current_start,
                            line_number - 1,
                            active_heading,
                            metadata,
                        )
                    )
                    current_lines = []
                    current_len = 0

                for piece, start_offset in self._split_long_line(line):
                    chunks.append(
                        TextChunk(
                            text=piece,
                            start_line=line_number,
                            end_line=line_number,
                            title=active_heading,
                            metadata={**metadata, "line_offset": start_offset},
                        )
                    )
                current_start = line_number + 1
                continue

            should_flush = current_lines and (
                current_len + line_len > self.max_chars or (not line.strip() and current_len > self.max_chars * 0.7)
            )
            if should_flush:
                chunks.append(
                    self._build_chunk(
                        current_lines,
                        current_start,
                        line_number - 1,
                        active_heading,
                        metadata,
                    )
                )
                overlap_lines = self._build_overlap(current_lines)
                current_lines = overlap_lines[:] if overlap_lines else []
                current_start = max(1, line_number - len(current_lines))
                current_len = sum(len(item) + 1 for item in current_lines)

            if not current_lines:
                current_start = line_number
            current_lines.append(line)
            current_len += line_len

        if current_lines:
            chunks.append(self._build_chunk(current_lines, current_start, len(lines), active_heading, metadata))

        return chunks

    def _split_long_line(self, line: str) -> List[Tuple[str, int]]:
        pieces: List[Tuple[str, int]] = []
        for start in range(0, len(line), self.max_chars):
            pieces.append((line[start : start + self.max_chars], start))
        return pieces

    def _build_overlap(self, lines: List[str]) -> List[str]:
        overlap: List[str] = []
        char_count = 0
        for line in reversed(lines):
            addition = len(line) + 1
            if char_count + addition > self.overlap_chars:
                break
            overlap.insert(0, line)
            char_count += addition
        return overlap

    def _build_chunk(
        self,
        lines: List[str],
        start_line: int,
        end_line: int,
        heading: Optional[str],
        metadata: Dict[str, Any],
    ) -> TextChunk:
        text = "\n".join(lines).strip()
        return TextChunk(text=text, start_line=start_line, end_line=end_line, title=heading, metadata=dict(metadata))
