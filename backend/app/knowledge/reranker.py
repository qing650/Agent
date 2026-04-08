"""Context reranking and filtering for better retrieval quality."""

from __future__ import annotations

import math
import re
from typing import List, Optional

from ..storage.storage import SearchResult


class BM25Reranker:
    """BM25 keyword reranker for retrieval results."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """Initialize BM25 parameters.
        
        Args:
            k1: Term frequency saturation parameter (default 1.5)
            b: Length normalization parameter (default 0.75)
        """
        self.k1 = k1
        self.b = b
        self.avg_doc_len = 0.0
        self.idf_cache: dict[str, float] = {}

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text for BM25 calculation."""
        normalized = text.lower()
        # 支持中文和英文混�?
        tokens = re.findall(r"[\u4e00-\u9fff]|[a-z0-9_]+", normalized)
        return tokens or []

    def _calculate_idf(self, token: str, total_docs: int, doc_frequency: int) -> float:
        """Calculate IDF (Inverse Document Frequency)."""
        if total_docs <= doc_frequency:
            return 0.0
        return math.log((total_docs - doc_frequency + 0.5) / (doc_frequency + 0.5) + 1.0)

    def rerank(
        self,
        query: str,
        results: List[SearchResult],
        k: Optional[int] = None,
    ) -> List[SearchResult]:
        """Rerank search results using BM25 + semantic score fusion.
        
        Args:
            query: Original query string
            results: Search results with existing scores
            k: Number of top results to return (default: all)
            
        Returns:
            Reranked results sorted by combined score
        """
        if not results:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return results[:k] if k else results

        # 计算文档统计
        total_docs = len(results)
        token_doc_freq: dict[str, int] = {}
        for result in results:
            seen_tokens = set()
            for token in self._tokenize(result.snippet):
                if token not in seen_tokens:
                    token_doc_freq[token] = token_doc_freq.get(token, 0) + 1
                    seen_tokens.add(token)

        # 计算每个结果的BM25分数
        reranked: List[tuple[SearchResult, float]] = []
        for result in results:
            tokens = self._tokenize(result.snippet)
            doc_len = len(tokens)

            bm25_score = 0.0
            for query_token in query_tokens:
                term_freq = tokens.count(query_token)
                if term_freq > 0:
                    doc_freq = token_doc_freq.get(query_token, 1)
                    idf = self._calculate_idf(query_token, total_docs, doc_freq)

                    # BM25公式
                    numerator = idf * term_freq * (self.k1 + 1)
                    denominator = term_freq + self.k1 * (
                        1 - self.b + self.b * (doc_len / max(self.avg_doc_len or 100, 1.0))
                    )
                    bm25_score += numerator / denominator

            # 融合原始语义分数（权�?0.3）和BM25分数（权�?0.7�?
            combined_score = result.score * 0.3 + (bm25_score / max(len(query_tokens), 1)) * 0.7
            reranked.append((result, combined_score))

        # 按融合分数排�?
        reranked.sort(key=lambda x: x[1], reverse=True)
        results_with_scores = [result for result, _ in reranked]

        return results_with_scores[:k] if k else results_with_scores

    def diversity_rerank(
        self,
        query: str,
        results: List[SearchResult],
        diversity_factor: float = 0.3,
        k: Optional[int] = None,
    ) -> List[SearchResult]:
        """Rerank to maximize diversity among top results.
        
        Args:
            query: Original query
            results: Search results
            diversity_factor: Weight for diversity (0-1, higher = more diversity)
            k: Number of results to return
            
        Returns:
            Diversity-optimized ranked results
        """
        if not results or len(results) < 2:
            return results[:k] if k else results

        # 先进行BM25重排
        ranked = self.rerank(query, results, k=None)

        # MMR (Maximal Marginal Relevance) 算法实现多样�?
        selected: List[SearchResult] = []
        remaining = ranked.copy()

        while remaining:
            if not selected:
                # 选择第一个（分数最高的�?
                selected.append(remaining.pop(0))
            else:
                # 计算每个剩余结果的多样性分�?
                best_idx = 0
                best_score = -float("inf")

                for idx, candidate in enumerate(remaining):
                    # 计算与已选择结果的最小相似度
                    min_similarity = 1.0
                    for selected_result in selected:
                        similarity = self._jaccard_similarity(
                            set(self._tokenize(candidate.snippet)),
                            set(self._tokenize(selected_result.snippet)),
                        )
                        min_similarity = min(min_similarity, similarity)

                    # MMR分数 = (1-λ) * 相关�?+ λ * (1 - 与已选最小相似度)
                    mmr_score = (1 - diversity_factor) * candidate.score + diversity_factor * (1 - min_similarity)

                    if mmr_score > best_score:
                        best_score = mmr_score
                        best_idx = idx

                selected.append(remaining.pop(best_idx))

            if k and len(selected) >= k:
                break

        return selected[:k] if k else selected

    @staticmethod
    def _jaccard_similarity(set1: set, set2: set) -> float:
        """Calculate Jaccard similarity between two sets."""
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0


class SemanticRelevanceFilter:
    """Filter low-confidence results based on semantic similarity."""

    def __init__(self, min_relevance: float = 0.5):
        """Initialize filter.
        
        Args:
            min_relevance: Minimum relevance score (0-1) to keep result
        """
        self.min_relevance = min_relevance

    def filter_results(
        self,
        query: str,
        results: List[SearchResult],
        min_relevance: Optional[float] = None,
    ) -> List[SearchResult]:
        """Filter results by relevance score.
        
        Args:
            query: Query for reference
            results: Results to filter
            min_relevance: Override minimum threshold
            
        Returns:
            Filtered results with only high-confidence matches
        """
        threshold = min_relevance if min_relevance is not None else self.min_relevance

        # 标准化分数到0-1范围
        if results:
            max_score = max(r.score for r in results) or 1.0
            filtered = [
                result
                for result in results
                if (result.score / max_score) >= threshold
            ]
            return filtered if filtered else results[:1]  # 至少保留1�?

        return results

    def group_by_source(
        self,
        results: List[SearchResult],
    ) -> dict[str, List[SearchResult]]:
        """Group results by their source document.
        
        Returns:
            Dict mapping source paths to result lists
        """
        grouped: dict[str, List[SearchResult]] = {}
        for result in results:
            if result.path not in grouped:
                grouped[result.path] = []
            grouped[result.path].append(result)
        return grouped

    def select_representative(
        self,
        results: List[SearchResult],
        max_per_source: int = 1,
    ) -> List[SearchResult]:
        """Select representative results from each source.
        
        Args:
            results: Input results
            max_per_source: Maximum results per source document
            
        Returns:
            Representative results, maintaining order
        """
        grouped = self.group_by_source(results)
        representatives: List[SearchResult] = []

        # 保持原始顺序
        seen_sources = set()
        for result in results:
            if result.path not in seen_sources:
                source_results = grouped[result.path]
                # 取该源的前max_per_source个结�?
                representatives.extend(source_results[:max_per_source])
                seen_sources.add(result.path)

        return representatives

