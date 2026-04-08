from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..services.novel_service import NovelService


class NovelFlow:
    """Thin workflow wrapper around novel service."""

    def __init__(self, service: NovelService):
        self.service = service

    def get_project(self, title: str, novel_id: str) -> Dict[str, Any]:
        return self.service.get_project(title=title, novel_id=novel_id)

    def list_projects(self) -> List[Dict[str, Any]]:
        return self.service.list_projects()

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
        return self.service.generate_outline(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            tags=tags,
            target_length=target_length,
            style_tags=style_tags,
        )

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
        return self.service.stream_generate_outline(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            tags=tags,
            target_length=target_length,
            style_tags=style_tags,
        )

    def get_outline(self, *, title: str, novel_id: str, note_id: Optional[str] = None) -> Dict[str, Any]:
        return self.service.get_outline(title=title, novel_id=novel_id, note_id=note_id)

    def update_outline(
        self,
        *,
        title: str,
        novel_id: str,
        note_id: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self.service.update_outline(
            title=title,
            novel_id=novel_id,
            note_id=note_id,
            content=content,
            tags=tags,
        )

    def delete_outline(self, *, title: str, novel_id: str, note_id: str) -> Dict[str, Any]:
        return self.service.delete_outline(title=title, novel_id=novel_id, note_id=note_id)

    def generate_chapters(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        num_chapters: int = 1,
        chapter_length: int = 3000,
    ) -> Dict[str, Any]:
        return self.service.generate_chapters(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            num_chapters=num_chapters,
            chapter_length=chapter_length,
        )

    def stream_generate_chapters(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        num_chapters: int = 1,
        chapter_length: int = 3000,
    ):
        return self.service.stream_generate_chapters(
            novel_id=novel_id,
            title=title,
            user_input=user_input,
            num_chapters=num_chapters,
            chapter_length=chapter_length,
        )

    def get_chapter(self, *, title: str, novel_id: str, note_id: str) -> Dict[str, Any]:
        return self.service.get_chapter(title=title, novel_id=novel_id, note_id=note_id)

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
        return self.service.update_chapter(
            title=title,
            novel_id=novel_id,
            note_id=note_id,
            content=content,
            chapter_title=chapter_title,
            summary=summary,
            next_chapter_prediction=next_chapter_prediction,
        )

    def delete_chapter(self, *, title: str, novel_id: str, note_id: str) -> Dict[str, Any]:
        return self.service.delete_chapter(title=title, novel_id=novel_id, note_id=note_id)
