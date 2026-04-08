from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

from ...core.llm import ChatLLM
from ...knowledge.compressor import ContextCompressor
from ...knowledge.reranker import BM25Reranker, SemanticRelevanceFilter
from ...storage.config import MemoryConfig
from ...storage.manager import MemoryManager
from ...storage.storage import SearchResult


SYSTEM_PROMPT = """You are a retrieval-augmented assistant grounded in evidence.

Core rules:
1. Answer ONLY based on provided knowledge and memory snippets.
2. When evidence is insufficient or conflicting, explicitly say so instead of guessing.
3. Always cite sources using tags like [K1], [K2], [M1] for knowledge and memory.
4. Be concise and direct.

Critical: If you cannot find sufficient evidence to answer confidently, respond with:
"I don't have enough information in my knowledge base to answer this question accurately."

Never fabricate details or make assumptions beyond the evidence."""


@dataclass
class ChatResponse:
    answer: str
    knowledge_results: List[SearchResult]
    memory_results: List[SearchResult]
    remembered: List[str]
    confidence: float


@dataclass
class PreparedChat:
    effective_user: str
    history: List[Dict[str, Any]]
    memory_hits: List[SearchResult]
    knowledge_hits: List[SearchResult]
    confidence: float


class ChatAgent:
    """Conversational agent with short-term and long-term memory."""

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        memory_manager: Optional[MemoryManager] = None,
        llm: Optional[ChatLLM] = None,
        history_limit: int = 8,
        top_k: int = 4,
        min_relevance: float = 0.5,
    ):
        self.memory_manager = memory_manager or MemoryManager(config=config)
        self.config = self.memory_manager.config
        self.llm = llm or ChatLLM()
        self.history_limit = history_limit
        self.top_k = top_k
        self.min_relevance = min_relevance
        self.reranker = BM25Reranker()
        self.filter = SemanticRelevanceFilter(min_relevance=min_relevance)
        self.compressor = ContextCompressor(max_chars=2000, max_sentences=15)

    def chat(
        self,
        question: str,
        session_id: str = "default",
        user_id: Optional[str] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = 2000,
    ) -> ChatResponse:
        prepared = self._prepare_chat(
            question=question,
            session_id=session_id,
            user_id=user_id,
            top_k=top_k,
            max_tokens=max_tokens,
        )
        answer, is_direct = self._generate_answer(
            question=question,
            history=prepared.history,
            memory_hits=prepared.memory_hits,
            knowledge_hits=prepared.knowledge_hits,
        )
        return self._finalize_chat(
            session_id=session_id,
            effective_user=prepared.effective_user,
            answer=answer,
            is_direct=is_direct,
            confidence=prepared.confidence,
            knowledge_hits=prepared.knowledge_hits,
            memory_hits=prepared.memory_hits,
        )

    def stream_chat(
        self,
        question: str,
        session_id: str = "default",
        user_id: Optional[str] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = 2000,
    ) -> Iterator[Dict[str, Any]]:
        prepared = self._prepare_chat(
            question=question,
            session_id=session_id,
            user_id=user_id,
            top_k=top_k,
            max_tokens=max_tokens,
        )

        answer = ""
        is_direct = False
        streamed = False

        if prepared.memory_hits or prepared.knowledge_hits:
            messages = self._build_messages(
                question=question,
                history=prepared.history,
                memory_hits=prepared.memory_hits,
                knowledge_hits=prepared.knowledge_hits,
            )
            parts: List[str] = []
            for chunk in self.llm.stream_generate(system_prompt=SYSTEM_PROMPT, messages=messages):
                streamed = True
                parts.append(chunk)
                yield {"type": "content", "data": chunk}

            streamed_answer = "".join(parts).strip()
            if streamed_answer:
                answer = self._ensure_source_appendix(streamed_answer, prepared.knowledge_hits, prepared.memory_hits)
                is_direct = True

        if not answer:
            answer, is_direct = self._generate_answer(
                question=question,
                history=prepared.history,
                memory_hits=prepared.memory_hits,
                knowledge_hits=prepared.knowledge_hits,
            )
            if answer:
                for chunk in self._iter_text_chunks(answer, preferred_size=120):
                    streamed = True
                    yield {"type": "content", "data": chunk}

        response = self._finalize_chat(
            session_id=session_id,
            effective_user=prepared.effective_user,
            answer=answer,
            is_direct=is_direct,
            confidence=prepared.confidence,
            knowledge_hits=prepared.knowledge_hits,
            memory_hits=prepared.memory_hits,
        )

        yield {
            "type": "done",
            "data": {
                "answer": response.answer,
                "remembered": response.remembered,
                "citations": [result.citation for result in response.knowledge_results],
                "confidence": response.confidence,
            },
        }

    def _iter_text_chunks(self, text: str, preferred_size: int = 120) -> Iterator[str]:
        if not text:
            return

        start = 0
        text_length = len(text)
        while start < text_length:
            end = min(text_length, start + preferred_size)
            if end < text_length:
                split_at = max(
                    text.rfind("\n", start, end),
                    text.rfind("。", start, end),
                    text.rfind("！", start, end),
                    text.rfind("？", start, end),
                    text.rfind(".", start, end),
                    text.rfind("!", start, end),
                    text.rfind("?", start, end),
                    text.rfind(" ", start, end),
                )
                if split_at >= start:
                    end = split_at + 1

            chunk = text[start:end]
            if chunk:
                yield chunk
            start = end

    def _prepare_chat(
        self,
        question: str,
        session_id: str,
        user_id: Optional[str],
        top_k: Optional[int],
        max_tokens: Optional[int],
    ) -> PreparedChat:
        effective_user = user_id or self.config.default_user_id
        k = top_k if top_k is not None else self.top_k
        history = self.memory_manager.load_recent_conversation(session_id, limit=self.history_limit)
        self.memory_manager.append_message(session_id, "user", question, user_id=effective_user)

        memory_hits = self.memory_manager.search_memory(question, user_id=effective_user, limit=k * 2)
        knowledge_hits = self.memory_manager.search_knowledge(question, user_id=effective_user, limit=k * 2)

        memory_hits = self.reranker.rerank(question, memory_hits, k=k)
        knowledge_hits = self.reranker.rerank(question, knowledge_hits, k=k)

        memory_hits = self.filter.filter_results(question, memory_hits, min_relevance=self.min_relevance)
        knowledge_hits = self.filter.filter_results(question, knowledge_hits, min_relevance=self.min_relevance)

        memory_hits = self.compressor.compress_results(memory_hits, question)
        knowledge_hits = self.compressor.compress_results(knowledge_hits, question)

        all_results = memory_hits + knowledge_hits
        truncated_results = self.compressor.truncate_to_token_limit(all_results, max_tokens=max_tokens)
        memory_hits = [result for result in truncated_results if result.source == "memory"]
        knowledge_hits = [result for result in truncated_results if result.source == "knowledge"]
        confidence = self._estimate_confidence(question, memory_hits, knowledge_hits)

        return PreparedChat(
            effective_user=effective_user,
            history=history,
            memory_hits=memory_hits,
            knowledge_hits=knowledge_hits,
            confidence=confidence,
        )

    def _build_messages(
        self,
        question: str,
        history: List[Dict[str, Any]],
        memory_hits: List[SearchResult],
        knowledge_hits: List[SearchResult],
    ) -> List[Dict[str, str]]:
        knowledge_context = self.compressor.format_context_prompt(knowledge_hits, prefix="K")
        memory_context = self.compressor.format_context_prompt(memory_hits, prefix="M")
        user_prompt = (
            f"Question: {question}\n\n"
            f"Knowledge base:\n{knowledge_context or 'None available'}\n\n"
            f"Long-term memory:\n{memory_context or 'None available'}\n\n"
            "Instructions: Answer based strictly on the provided evidence. "
            "If evidence is insufficient, explicitly state that."
        )
        messages = [{"role": item["role"], "content": item["content"]} for item in history]
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _finalize_chat(
        self,
        session_id: str,
        effective_user: str,
        answer: str,
        is_direct: bool,
        confidence: float,
        knowledge_hits: List[SearchResult],
        memory_hits: List[SearchResult],
    ) -> ChatResponse:
        self.memory_manager.append_message(
            session_id,
            "assistant",
            answer,
            user_id=effective_user,
            metadata={
                "citations": [result.citation for result in knowledge_hits + memory_hits],
                "confidence": confidence,
                "is_direct": is_direct,
            },
        )
        remembered = self.memory_manager.remember_from_conversation(session_id, user_id=effective_user, max_messages=6)
        self.memory_manager.summarize_to_daily_memory(session_id, user_id=effective_user, max_messages=10)
        return ChatResponse(
            answer=answer,
            knowledge_results=knowledge_hits,
            memory_results=memory_hits,
            remembered=remembered,
            confidence=confidence,
        )

    def _estimate_confidence(
        self,
        question: str,
        memory_hits: List[SearchResult],
        knowledge_hits: List[SearchResult],
    ) -> float:
        if not memory_hits and not knowledge_hits:
            return 0.0

        total_hits = len(memory_hits) + len(knowledge_hits)
        avg_score = (
            sum(result.score for result in memory_hits + knowledge_hits) / total_hits
            if total_hits > 0
            else 0.0
        )
        has_memory = len(memory_hits) > 0
        has_knowledge = len(knowledge_hits) > 0
        source_bonus = 0.2 if (has_memory and has_knowledge) else 0.0
        return min(0.95, avg_score + source_bonus)

    def _generate_answer(
        self,
        question: str,
        history: List[Dict[str, Any]],
        memory_hits: List[SearchResult],
        knowledge_hits: List[SearchResult],
    ) -> tuple[str, bool]:
        if not memory_hits and not knowledge_hits:
            return self._no_evidence_response(question), False

        llm_answer = self._generate_with_llm(question, history, memory_hits, knowledge_hits)
        if llm_answer:
            return self._ensure_source_appendix(llm_answer, knowledge_hits, memory_hits), True

        return self._fallback_answer(question, memory_hits, knowledge_hits), False

    def _generate_with_llm(
        self,
        question: str,
        history: List[Dict[str, Any]],
        memory_hits: List[SearchResult],
        knowledge_hits: List[SearchResult],
    ) -> Optional[str]:
        if not self.llm.available:
            return None

        messages = self._build_messages(
            question=question,
            history=history,
            memory_hits=memory_hits,
            knowledge_hits=knowledge_hits,
        )
        return self.llm.generate(system_prompt=SYSTEM_PROMPT, messages=messages)

    def _no_evidence_response(self, question: str) -> str:
        return (
            "I don't have enough information in my knowledge base to answer this question accurately. "
            f"The question was: '{question}'\n\n"
            "Please provide relevant documents or information, or try rephrasing your question."
        )

    def _fallback_answer(
        self,
        question: str,
        memory_hits: List[SearchResult],
        knowledge_hits: List[SearchResult],
    ) -> str:
        candidates = [(f"K{idx}", result) for idx, result in enumerate(knowledge_hits, start=1)]
        candidates += [(f"M{idx}", result) for idx, result in enumerate(memory_hits, start=1)]

        if not candidates:
            return self._no_evidence_response(question)

        snippets = []
        for tag, result in candidates[:5]:
            snippet = result.snippet.strip()
            if snippet:
                snippets.append(f"[{tag}] {snippet}")

        if not snippets:
            return self._no_evidence_response(question)

        answer = "Based on available evidence:\n\n"
        answer += "\n\n".join(snippets)
        answer += "\n\nSources:\n"
        answer += "\n".join(f"- [{tag}] {result.citation}" for tag, result in candidates[:4])
        return answer

    def _ensure_source_appendix(
        self,
        answer: str,
        knowledge_hits: List[SearchResult],
        memory_hits: List[SearchResult],
    ) -> str:
        source_lines = []
        for idx, result in enumerate(knowledge_hits, start=1):
            source_lines.append(f"- [K{idx}] {result.citation}")
        for idx, result in enumerate(memory_hits, start=1):
            source_lines.append(f"- [M{idx}] {result.citation}")

        if not source_lines:
            return answer
        if "Sources:" in answer or "[K" in answer or "[M" in answer:
            return answer
        return f"{answer}\n\n**Sources:**\n" + "\n".join(source_lines)
