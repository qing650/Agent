"""Context compression and optimization for LLM input."""

from __future__ import annotations

import re
from typing import List, Optional

from ..storage.storage import SearchResult


class ContextCompressor:
    """Compress and optimize retrieval context for LLM consumption."""

    def __init__(self, max_chars: int = 2000, max_sentences: int = 15):
        """Initialize compressor.
        
        Args:
            max_chars: Maximum characters per compressed context
            max_sentences: Maximum sentences per result
        """
        self.max_chars = max_chars
        self.max_sentences = max_sentences

    def compress_results(
        self,
        results: List[SearchResult],
        query: str,
        preserve_full_context: bool = False,
    ) -> List[SearchResult]:
        """Compress results to reduce token usage.
        
        Args:
            results: Search results to compress
            query: Original query for relevance-based extraction
            preserve_full_context: If True, add full context in 'content' field
            
        Returns:
            Compressed results
        """
        compressed: List[SearchResult] = []

        for result in results:
            # 提取最相关的句�?
            key_sentences = self._extract_key_sentences(
                result.snippet, query, self.max_sentences
            )
            condensed_snippet = " ".join(key_sentences)

            # 创建压缩结果
            compressed_result = SearchResult(
                path=result.path,
                source=result.source,
                visibility=result.visibility,
                score=result.score,
                snippet=condensed_snippet[:self.max_chars],
                start_line=result.start_line,
                end_line=result.end_line,
                user_id=result.user_id,
                title=result.title,
                metadata=result.metadata,
                content=result.snippet if preserve_full_context else "",  # 保留完整内容
            )
            compressed.append(compressed_result)

        return compressed

    def _extract_key_sentences(
        self,
        text: str,
        query: str,
        max_sentences: int,
    ) -> List[str]:
        """Extract most relevant sentences from text.
        
        Args:
            text: Source text
            query: Query for relevance scoring
            max_sentences: Maximum sentences to extract
            
        Returns:
            Most relevant sentences
        """
        # 分句 - 支持中文和英�?
        sentences = [
            s.strip()
            for s in re.split(r"[\u3002\uFF01\uFF1F!?\n]+", text)
            if s.strip()
        ]

        if len(sentences) <= max_sentences:
            return sentences

        # 计算每句的相关度分数
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return sentences[:max_sentences]

        scored_sentences: List[tuple[int, str, float]] = []
        for idx, sentence in enumerate(sentences):
            score = self._score_sentence(sentence, query_tokens)
            scored_sentences.append((idx, sentence, score))

        # 选择分数最高的句子
        scored_sentences.sort(key=lambda x: x[2], reverse=True)
        top_sentences = scored_sentences[:max_sentences]

        # 恢复原始顺序
        top_sentences.sort(key=lambda x: x[0])
        return [s for _, s, _ in top_sentences]

    def _score_sentence(self, sentence: str, query_tokens: List[str]) -> float:
        """Score sentence relevance to query."""
        sentence_lower = sentence.lower()
        score = 0.0

        for token in query_tokens:
            # 计数匹配次数
            count = sentence_lower.count(token)
            # TF-IDF近似：出现次数越多分数越高，但有衰减
            score += count * (1.0 / (1.0 + 0.1 * count))

        # 长度归一�?- 偏向适中长度的句�?
        length = len(sentence.split())
        if length > 0:
            length_factor = 1.0 if 10 <= length <= 50 else 0.8
            score *= length_factor

        return score

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize text."""
        normalized = text.lower()
        tokens = re.findall(r"[\u4e00-\u9fff]|[a-z0-9_]+", normalized)
        return tokens

    def format_context_prompt(
        self,
        results: List[SearchResult],
        prefix: str = "K",
        include_scores: bool = False,
    ) -> str:
        """Format compressed results into a prompt-friendly string.
        
        Args:
            results: Compressed search results
            prefix: Prefix for citations (e.g., 'K' for knowledge)
            include_scores: Whether to include relevance scores
            
        Returns:
            Formatted context string
        """
        if not results:
            return ""

        lines: List[str] = []
        for idx, result in enumerate(results, start=1):
            citation = f"[{prefix}{idx}]"

            # 构建上下文块
            block = f"{citation} {result.title or result.path}"
            if include_scores:
                block += f" (relevance: {result.score:.2f})"
            lines.append(block)
            lines.append(result.snippet)
            lines.append("")

        return "\n".join(lines).strip()

    def create_evidence_summary(
        self,
        results: List[SearchResult],
        max_results: int = 3,
    ) -> str:
        """Create a concise evidence summary.
        
        Args:
            results: Search results
            max_results: Maximum results to include
            
        Returns:
            Markdown-formatted evidence summary
        """
        if not results:
            return "No relevant evidence found."

        summary_parts: List[str] = []
        summary_parts.append("### Retrieved Evidence\n")

        for idx, result in enumerate(results[:max_results], start=1):
            summary_parts.append(f"**[{idx}] {result.title or result.path}**")
            summary_parts.append(f"> {result.snippet}")
            summary_parts.append("")

        return "\n".join(summary_parts)

    def estimate_token_count(self, text: str, model: str = "gpt-3.5-turbo") -> int:
        """Estimate token count (rough approximation).
        
        Args:
            text: Input text
            model: Model name for token estimation
            
        Returns:
            Approximate token count
        """
        # 粗略估计：英文平�?字符=1token，中文平�?-2字符=1token
        english_chars = sum(1 for c in text if ord(c) < 128)
        chinese_chars = sum(1 for c in text if ord(c) >= 0x4e00 and ord(c) <= 0x9fff)

        english_tokens = english_chars / 4
        chinese_tokens = chinese_chars

        return int(english_tokens + chinese_tokens + 1)

    def truncate_to_token_limit(
        self,
        results: List[SearchResult],
        max_tokens: int = 2000,
        preserve_last: bool = True,
    ) -> List[SearchResult]:
        """Truncate results to fit within token limit.
        
        Args:
            results: Results to truncate
            max_tokens: Maximum token budget
            preserve_last: If True, preserve at least the first result
            
        Returns:
            Truncated results
        """
        if not results:
            return []

        token_budget = max_tokens
        selected_results: List[SearchResult] = []

        for result in results:
            # 估计这个结果的token�?
            snippet_tokens = self.estimate_token_count(result.snippet)
            metadata_tokens = 10  # 源信息和元数�?

            if snippet_tokens + metadata_tokens <= token_budget:
                selected_results.append(result)
                token_budget -= (snippet_tokens + metadata_tokens)
            elif preserve_last and not selected_results:
                # 至少保留一�?
                selected_results.append(result)
                break
            else:
                # 预算用尽
                break

        return selected_results

