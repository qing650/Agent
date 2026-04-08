from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from ..agents.chat.agent import ChatResponse
from .runtime_service import AppRuntime


class ChatService:
    """Application-facing orchestration for chat endpoints."""

    def __init__(self, runtime: AppRuntime):
        self.runtime = runtime

    def chat(
        self,
        question: str,
        session_id: str,
        user_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> ChatResponse:
        return self.runtime.chat_agent.chat(
            question=question,
            session_id=session_id,
            user_id=user_id,
            top_k=top_k,
        )

    def stream_chat(
        self,
        question: str,
        session_id: str,
        user_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        return self.runtime.chat_agent.stream_chat(
            question=question,
            session_id=session_id,
            user_id=user_id,
            top_k=top_k,
        )

    def serialize_chat_response(self, response: ChatResponse) -> Dict[str, Any]:
        return {
            "success": True,
            "answer": response.answer,
            "remembered": response.remembered,
            "knowledge_results": [result.to_dict() for result in response.knowledge_results],
            "memory_results": [result.to_dict() for result in response.memory_results],
            "confidence": response.confidence,
            "errorMessage": None,
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        history = self.runtime.memory_manager.get_session_history(session_id)
        session = self.runtime.memory_manager.conversations.get_session(session_id)
        if session is None:
            return None
        return {
            "session": session,
            "history": history,
            "message_count": len(history),
        }

    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.runtime.memory_manager.list_sessions(user_id=user_id)

    def clear_session(self, session_id: str) -> bool:
        return self.runtime.memory_manager.clear_session(session_id)
