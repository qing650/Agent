from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from ..agents.chat.agent import ChatResponse
from ..services.chat_service import ChatService


class ChatFlow:
    """Thin workflow wrapper around chat service."""

    def __init__(self, service: ChatService):
        self.service = service

    def chat(
        self,
        question: str,
        session_id: str,
        user_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> ChatResponse:
        return self.service.chat(question=question, session_id=session_id, user_id=user_id, top_k=top_k)

    def stream_chat(
        self,
        question: str,
        session_id: str,
        user_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        return self.service.stream_chat(question=question, session_id=session_id, user_id=user_id, top_k=top_k)

    def serialize_chat_response(self, response: ChatResponse) -> Dict[str, Any]:
        return self.service.serialize_chat_response(response)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.service.get_session(session_id)

    def list_sessions(self, user_id: Optional[str] = None):
        return self.service.list_sessions(user_id=user_id)

    def clear_session(self, session_id: str) -> bool:
        return self.service.clear_session(session_id)
