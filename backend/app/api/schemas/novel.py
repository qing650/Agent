from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class OutlineGenerateRequest(BaseModel):
    novel_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    user_input: str = Field(min_length=1, max_length=8000)
    tags: List[str] = Field(default_factory=list)
    target_length: int = Field(default=3000, ge=200, le=20000)
    style_tags: Dict[str, str] = Field(default_factory=dict)


class OutlineUpdateRequest(BaseModel):
    novel_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    note_id: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    tags: Optional[List[str]] = None


class ChapterGenerateRequest(BaseModel):
    novel_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    user_input: str = Field(default="", max_length=8000)
    num_chapters: int = Field(default=1, ge=1, le=20)
    chapter_length: int = Field(default=3000, ge=300, le=20000)


class ChapterUpdateRequest(BaseModel):
    novel_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    note_id: str = Field(min_length=1, max_length=200)
    content: Optional[str] = None
    chapter_title: Optional[str] = None
    summary: Optional[str] = None
    next_chapter_prediction: Optional[str] = None
