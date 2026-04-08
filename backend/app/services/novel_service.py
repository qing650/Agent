from __future__ import annotations

from typing import Any, Dict, List, Optional

from .runtime_service import AppRuntime


class NovelService:
    """Application-facing orchestration for novel endpoints."""

    def __init__(self, runtime: AppRuntime):
        self.runtime = runtime

    def get_project(self, title: str, novel_id: str) -> Dict[str, Any]:
        return self.runtime.novel_agent.get_project(title=title, novel_id=novel_id)

    def list_projects(self) -> List[Dict[str, Any]]:
        return self.runtime.novel_agent.list_projects()

    def generate_outline(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        tags: Optional[List[str]] = None,
        target_length: int = 3000,
        style_tags: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        result = self.runtime.novel_agent.generate_outline(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            tags=tags,
            target_length=target_length,
            style_tags=style_tags,
        )
        return {"note_id": result.note_id, "content": result.content}

    def stream_generate_outline(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        tags: Optional[List[str]] = None,
        target_length: int = 3000,
        style_tags: Optional[Dict[str, str]] = None,
    ):
        return self.runtime.novel_agent.stream_generate_outline(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            tags=tags,
            target_length=target_length,
            style_tags=style_tags,
        )

    def get_outline(self, *, title: str, novel_id: str, note_id: Optional[str] = None) -> Dict[str, Any]:
        return self.runtime.novel_agent.get_outline(title=title, novel_id=novel_id, note_id=note_id)

    def update_outline(
        self,
        *,
        title: str,
        novel_id: str,
        note_id: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self.runtime.novel_agent.update_outline(
            title=title,
            novel_id=novel_id,
            note_id=note_id,
            content=content,
            tags=tags,
        )
        return {"status": "success"}

    def delete_outline(self, *, title: str, novel_id: str, note_id: str) -> Dict[str, Any]:
        return {
            "status": "success",
            "deleted": self.runtime.novel_agent.delete_outline(title=title, novel_id=novel_id, note_id=note_id),
        }

    def generate_chapters(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        num_chapters: int = 1,
        chapter_length: int = 3000,
    ) -> Dict[str, Any]:
        chapters = self.runtime.novel_agent.generate_chapters(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            num_chapters=num_chapters,
            chapter_length=chapter_length,
        )
        return {"generated_chapters": [item.to_dict() for item in chapters]}

    def stream_generate_chapters(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        num_chapters: int = 1,
        chapter_length: int = 3000,
    ):
        return self.runtime.novel_agent.stream_generate_chapters(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            num_chapters=num_chapters,
            chapter_length=chapter_length,
        )

    def get_chapter(self, *, title: str, novel_id: str, note_id: str) -> Dict[str, Any]:
        return self.runtime.novel_agent.get_chapter(title=title, novel_id=novel_id, note_id=note_id)

    def update_chapter(
        self,
        *,
        title: str,
        novel_id: str,
        note_id: str,
        content: Optional[str] = None,
        chapter_title: Optional[str] = None,
        summary: Optional[str] = None,
        next_chapter_prediction: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.runtime.novel_agent.update_chapter(
            title=title,
            novel_id=novel_id,
            note_id=note_id,
            content=content,
            chapter_title=chapter_title,
            summary=summary,
            next_chapter_prediction=next_chapter_prediction,
        )
        return {"status": "success"}

    def delete_chapter(self, *, title: str, novel_id: str, note_id: str) -> Dict[str, Any]:
        return {
            "status": "success",
            "deleted": self.runtime.novel_agent.delete_chapter(title=title, novel_id=novel_id, note_id=note_id),
        }
