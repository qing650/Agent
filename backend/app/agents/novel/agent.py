from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ...core.llm import ChatLLM
from ...storage.config import MemoryConfig
from .prompts import (
    CHAPTER_PROMPT,
    CHAPTER_REVIEW_PROMPT,
    CHAPTER_REVIEW_SYSTEM_PROMPT,
    CHAPTER_START_PROMPT,
    CHAPTER_SYSTEM_PROMPT,
    OUTLINE_PROMPT,
    OUTLINE_SYSTEM_PROMPT,
)


@dataclass
class OutlineResult:
    note_id: str
    content: str


@dataclass
class ChapterResult:
    note_id: str
    title: str
    summary: str
    content: str
    next_chapter_prediction: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.note_id,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "next_chapter_prediction": self.next_chapter_prediction,
        }


class NovelAgent:
    """Native novel generation agent integrated with the project layout."""

    def __init__(self, config: Optional[MemoryConfig] = None, llm: Optional[ChatLLM] = None):
        self.config = config or MemoryConfig()
        self.llm = llm or ChatLLM()
        self.workspace_root = self.config.get_workspace_root() / "novels"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def get_project(self, title: str, novel_id: str) -> Dict[str, Any]:
        return self._load_project(title=title, novel_id=novel_id)

    def list_projects(self) -> List[Dict[str, Any]]:
        projects: List[Dict[str, Any]] = []
        for path in self.workspace_root.glob("*/project_data.json"):
            try:
                project = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            projects.append(
                {
                    "novel_id": project.get("novel_id", ""),
                    "title": project.get("title", ""),
                    "outline_id": project.get("outline_id"),
                    "chapter_count": len(project.get("chapters", [])),
                    "created_at": project.get("created_at"),
                    "updated_at": project.get("updated_at"),
                }
            )
        projects.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return projects

    def generate_outline(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        tags: Optional[List[str]] = None,
        target_length: int = 3000,
        style_tags: Optional[Dict[str, str]] = None,
    ) -> OutlineResult:
        self._require_llm("生成大纲")
        project = self._load_project(title=title, novel_id=novel_id)
        prompt = OUTLINE_PROMPT.format(
            user_input=user_input.strip(),
            title=title.strip(),
            tags="，".join(tags or []) or "无",
            style_requirements=self._format_style_tags(style_tags),
            target_length=target_length,
        )
        content = self._generate_text(OUTLINE_SYSTEM_PROMPT, prompt)
        note_id = self._next_note_id(project, "outline")
        note_path = self._outline_dir(title, novel_id) / f"{note_id}.md"
        self._write_markdown_note(
            note_path=note_path,
            note_id=note_id,
            title=f"{title}-大纲",
            note_type="outline",
            tags=tags or ["outline"],
            content=content,
        )
        project["outline_id"] = note_id
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)
        return OutlineResult(note_id=note_id, content=content)

    def stream_generate_outline(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        tags: Optional[List[str]] = None,
        target_length: int = 3000,
        style_tags: Optional[Dict[str, str]] = None,
    ) -> Iterator[Dict[str, Any]]:
        self._require_llm("生成大纲")
        project = self._load_project(title=title, novel_id=novel_id)
        prompt = OUTLINE_PROMPT.format(
            user_input=user_input.strip(),
            title=title.strip(),
            tags="，".join(tags or []) or "无",
            style_requirements=self._format_style_tags(style_tags),
            target_length=target_length,
        )

        parts: List[str] = []
        for chunk in self.llm.stream_generate(
            OUTLINE_SYSTEM_PROMPT,
            [{"role": "user", "content": prompt}],
        ):
            parts.append(chunk)
            yield {"type": "content", "data": chunk}

        content = "".join(parts).strip()
        if not content:
            raise RuntimeError("LLM generation returned empty content")

        note_id = self._next_note_id(project, "outline")
        note_path = self._outline_dir(title, novel_id) / f"{note_id}.md"
        self._write_markdown_note(
            note_path=note_path,
            note_id=note_id,
            title=f"{title}-大纲",
            note_type="outline",
            tags=tags or ["outline"],
            content=content,
        )
        project["outline_id"] = note_id
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)

        yield {"type": "done", "data": {"note_id": note_id, "content": content}}

    def get_outline(self, *, title: str, novel_id: str, note_id: Optional[str] = None) -> Dict[str, Any]:
        project = self._load_project(title=title, novel_id=novel_id)
        outline_id = note_id or project.get("outline_id")
        if not outline_id:
            raise FileNotFoundError("Outline not found")
        note_path = self._outline_dir(title, novel_id) / f"{outline_id}.md"
        content = self._read_note_body(note_path)
        return {"note_id": outline_id, "content": content}

    def update_outline(
        self,
        *,
        title: str,
        novel_id: str,
        note_id: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> None:
        note_path = self._outline_dir(title, novel_id) / f"{note_id}.md"
        note = self._read_note(note_path)
        self._write_markdown_note(
            note_path=note_path,
            note_id=note_id,
            title=note["title"],
            note_type="outline",
            tags=tags if tags is not None else note.get("tags", []),
            content=content,
            created_at=note.get("created_at"),
        )
        self._touch_project(title, novel_id)

    def delete_outline(self, *, title: str, novel_id: str, note_id: str) -> bool:
        project = self._load_project(title=title, novel_id=novel_id)
        note_path = self._outline_dir(title, novel_id) / f"{note_id}.md"
        if not note_path.exists():
            return False
        note_path.unlink()
        if project.get("outline_id") == note_id:
            project["outline_id"] = None
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)
        return True

    def generate_chapters(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        num_chapters: int = 1,
        chapter_length: int = 3000,
    ) -> List[ChapterResult]:
        self._require_llm("生成章节")
        generated: List[ChapterResult] = []
        current_input = user_input
        for _ in range(num_chapters):
            chapter = self._generate_single_chapter(
                novel_id=novel_id,
                title=title,
                user_input=current_input,
                chapter_length=chapter_length,
            )
            generated.append(chapter)
            current_input = ""
        return generated

    def stream_generate_chapters(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        num_chapters: int = 1,
        chapter_length: int = 3000,
    ) -> Iterator[Dict[str, Any]]:
        self._require_llm("生成章节")
        generated: List[Dict[str, Any]] = []
        current_input = user_input

        for index in range(num_chapters):
            yield {"type": "status", "data": f"正在生成第 {index + 1} 章..."}
            chapter = yield from self._generate_single_chapter_streaming(
                novel_id=novel_id,
                title=title,
                user_input=current_input,
                chapter_length=chapter_length,
            )
            chapter_dict = chapter.to_dict()
            generated.append(chapter_dict)
            yield {"type": "chapter_done", "data": chapter_dict}
            current_input = ""

        yield {"type": "done", "data": {"generated_chapters": generated}}

    def get_chapter(self, *, title: str, novel_id: str, note_id: str) -> Dict[str, Any]:
        note_path = self._chapter_dir(title, novel_id) / f"{note_id}.md"
        note = self._read_note(note_path)
        return {
            "id": note_id,
            "title": note.get("title", ""),
            "summary": self._first_tag(note),
            "content": self._read_note_body(note_path),
        }

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
    ) -> None:
        project = self._load_project(title=title, novel_id=novel_id)
        note_path = self._chapter_dir(title, novel_id) / f"{note_id}.md"
        note = self._read_note(note_path)
        body = self._read_note_body(note_path)

        chapter_meta = self._find_chapter(project, note_id)
        updated_summary = summary if summary is not None else chapter_meta.get("summary", self._first_tag(note))
        updated_prediction = (
            next_chapter_prediction
            if next_chapter_prediction is not None
            else chapter_meta.get("next_chapter_prediction", "")
        )
        updated_title = chapter_title if chapter_title is not None else note.get("title", note_id)
        updated_content = content if content is not None else body

        self._write_markdown_note(
            note_path=note_path,
            note_id=note_id,
            title=updated_title,
            note_type="chapter",
            tags=[updated_summary] if updated_summary else [],
            content=updated_content,
            created_at=note.get("created_at"),
        )

        chapter_meta.update(
            {
                "title": updated_title,
                "summary": updated_summary,
                "next_chapter_prediction": updated_prediction,
                "updated_at": self._now_iso(),
            }
        )
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)

    def delete_chapter(self, *, title: str, novel_id: str, note_id: str) -> bool:
        project = self._load_project(title=title, novel_id=novel_id)
        note_path = self._chapter_dir(title, novel_id) / f"{note_id}.md"
        if not note_path.exists():
            return False
        note_path.unlink()
        project["chapters"] = [item for item in project.get("chapters", []) if item.get("id") != note_id]
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)
        return True

    def _generate_single_chapter(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        chapter_length: int,
    ) -> ChapterResult:
        project = self._load_project(title=title, novel_id=novel_id)
        outline = self.get_outline(title=title, novel_id=novel_id)["content"]
        chapters = project.get("chapters", [])
        prev_chapter = "无"
        prev_summaries = "无"
        if chapters:
            last_chapter = self.get_chapter(title=title, novel_id=novel_id, note_id=chapters[-1]["id"])
            prev_chapter = f"【{last_chapter['title']}】\n...{last_chapter['content'][-800:]}"
            prev_summaries = "\n".join(
                f"【{item.get('title', '未知章节')}】\n{item.get('summary', '')}"
                for item in chapters[-5:]
            )

        prompt = self._build_chapter_prompt(
            outline=outline,
            prev_chapter=prev_chapter,
            prev_summaries=prev_summaries,
            user_input=user_input or (chapters[-1].get("next_chapter_prediction", "") if chapters else "无"),
            chapter_length=chapter_length,
            is_first_chapter=not chapters,
            chapter_history="无",
            evaluation="无",
        )

        review_feedback = "无"
        response_data: Optional[Dict[str, Any]] = None
        for _ in range(3):
            raw = self._generate_text(CHAPTER_SYSTEM_PROMPT, prompt, temperature=0.6, max_tokens=chapter_length * 2)
            response_data = self._parse_json_response(raw)
            review_feedback = self._review_chapter(
                outline=outline,
                prev_chapter=prev_chapter,
                prev_summaries=prev_summaries,
                chapter_content=response_data.get("content", ""),
            )
            if "【通过】" in review_feedback:
                break
            prompt = self._build_chapter_prompt(
                outline=outline,
                prev_chapter=prev_chapter,
                prev_summaries=prev_summaries,
                user_input=user_input or (chapters[-1].get("next_chapter_prediction", "") if chapters else "无"),
                chapter_length=chapter_length,
                is_first_chapter=not chapters,
                chapter_history=response_data.get("content", "无"),
                evaluation=review_feedback,
            )

        if response_data is None:
            raise RuntimeError("Chapter generation failed")

        note_id = self._next_note_id(project, "chapter")
        note_path = self._chapter_dir(title, novel_id) / f"{note_id}.md"
        chapter_title = str(response_data.get("title", "未知章节")).strip() or "未知章节"
        summary = str(response_data.get("summary", "")).strip()
        content = str(response_data.get("content", "")).strip()
        next_prediction = str(response_data.get("next_chapter_prediction", "")).strip()

        self._write_markdown_note(
            note_path=note_path,
            note_id=note_id,
            title=chapter_title,
            note_type="chapter",
            tags=[summary] if summary else [],
            content=content,
        )

        chapter_meta = {
            "id": note_id,
            "title": chapter_title,
            "summary": summary,
            "next_chapter_prediction": next_prediction,
            "created_at": self._now_iso(),
            "updated_at": self._now_iso(),
        }
        project.setdefault("chapters", []).append(chapter_meta)
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)

        return ChapterResult(
            note_id=note_id,
            title=chapter_title,
            summary=summary,
            content=content,
            next_chapter_prediction=next_prediction,
        )

    def _generate_single_chapter_streaming(
        self,
        *,
        novel_id: str,
        title: str,
        user_input: str,
        chapter_length: int,
    ) -> Iterator[Dict[str, Any]]:
        project = self._load_project(title=title, novel_id=novel_id)
        outline = self.get_outline(title=title, novel_id=novel_id)["content"]
        chapters = project.get("chapters", [])
        prev_chapter = "无"
        prev_summaries = "无"
        if chapters:
            last_chapter = self.get_chapter(title=title, novel_id=novel_id, note_id=chapters[-1]["id"])
            prev_chapter = f"【{last_chapter['title']}】\n...{last_chapter['content'][-800:]}"
            prev_summaries = "\n".join(
                f"【{item.get('title', '未知章节')}】\n{item.get('summary', '')}"
                for item in chapters[-5:]
            )

        prompt = self._build_chapter_prompt(
            outline=outline,
            prev_chapter=prev_chapter,
            prev_summaries=prev_summaries,
            user_input=user_input or (chapters[-1].get("next_chapter_prediction", "") if chapters else "无"),
            chapter_length=chapter_length,
            is_first_chapter=not chapters,
            chapter_history="无",
            evaluation="无",
        )

        review_feedback = "无"
        response_data: Optional[Dict[str, Any]] = None

        for attempt in range(3):
            emit_content = attempt == 0
            if emit_content:
                yield {"type": "chapter_start", "data": {"attempt": attempt + 1}}
            else:
                yield {"type": "status", "data": f"正在修订第 {attempt + 1} 轮生成结果..."}

            raw, streamed_content = yield from self._stream_chapter_json(
                prompt=prompt,
                emit_content=emit_content,
                chapter_length=chapter_length,
            )
            if emit_content and not streamed_content.strip():
                yield {"type": "status", "data": "本轮未能提取正文流，已继续完成生成。"}

            response_data = self._parse_json_response(raw)
            review_feedback = self._review_chapter(
                outline=outline,
                prev_chapter=prev_chapter,
                prev_summaries=prev_summaries,
                chapter_content=response_data.get("content", ""),
            )
            yield {"type": "review", "data": review_feedback}
            if "【通过】" in review_feedback:
                break

            prompt = self._build_chapter_prompt(
                outline=outline,
                prev_chapter=prev_chapter,
                prev_summaries=prev_summaries,
                user_input=user_input or (chapters[-1].get("next_chapter_prediction", "") if chapters else "无"),
                chapter_length=chapter_length,
                is_first_chapter=not chapters,
                chapter_history=response_data.get("content", "无"),
                evaluation=review_feedback,
            )

        if response_data is None:
            raise RuntimeError("Chapter generation failed")

        note_id = self._next_note_id(project, "chapter")
        note_path = self._chapter_dir(title, novel_id) / f"{note_id}.md"
        chapter_title = str(response_data.get("title", "未知章节")).strip() or "未知章节"
        summary = str(response_data.get("summary", "")).strip()
        content = str(response_data.get("content", "")).strip()
        next_prediction = str(response_data.get("next_chapter_prediction", "")).strip()

        self._write_markdown_note(
            note_path=note_path,
            note_id=note_id,
            title=chapter_title,
            note_type="chapter",
            tags=[summary] if summary else [],
            content=content,
        )

        chapter_meta = {
            "id": note_id,
            "title": chapter_title,
            "summary": summary,
            "next_chapter_prediction": next_prediction,
            "created_at": self._now_iso(),
            "updated_at": self._now_iso(),
        }
        project.setdefault("chapters", []).append(chapter_meta)
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)

        yield {
            "type": "chapter_finalized",
            "data": {
                "id": note_id,
                "title": chapter_title,
                "summary": summary,
                "content": content,
                "next_chapter_prediction": next_prediction,
            },
        }
        return ChapterResult(
            note_id=note_id,
            title=chapter_title,
            summary=summary,
            content=content,
            next_chapter_prediction=next_prediction,
        )

    def _stream_chapter_json(
        self,
        *,
        prompt: str,
        emit_content: bool,
        chapter_length: int,
    ) -> Iterator[Dict[str, Any]]:
        raw_parts: List[str] = []
        content_parts: List[str] = []
        parser = self._create_json_field_stream_parser("content")

        for chunk in self.llm.stream_generate(
            CHAPTER_SYSTEM_PROMPT,
            [{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=chapter_length * 2,
        ):
            raw_parts.append(chunk)
            if emit_content:
                extracted = parser.send(chunk)
                if extracted:
                    content_parts.append(extracted)
                    yield {"type": "content", "data": extracted}

        raw = "".join(raw_parts).strip()
        if not raw:
            raise RuntimeError("LLM generation returned empty content")
        return raw, "".join(content_parts)

    def _build_chapter_prompt(
        self,
        *,
        outline: str,
        prev_chapter: str,
        prev_summaries: str,
        user_input: str,
        chapter_length: int,
        is_first_chapter: bool,
        chapter_history: str,
        evaluation: str,
    ) -> str:
        if is_first_chapter:
            return CHAPTER_START_PROMPT.format(
                outline=outline,
                chapter_history=chapter_history,
                evaluation=evaluation,
                user_input=user_input or "无",
                chapter_length=chapter_length,
            )
        return CHAPTER_PROMPT.format(
            outline=outline,
            prev_chapter=prev_chapter,
            prev_summaries=prev_summaries,
            chapter_history=chapter_history,
            evaluation=evaluation,
            user_input=user_input or "无",
            chapter_length=chapter_length,
        )

    def _review_chapter(self, *, outline: str, prev_chapter: str, prev_summaries: str, chapter_content: str) -> str:
        return self._generate_text(
            CHAPTER_REVIEW_SYSTEM_PROMPT,
            CHAPTER_REVIEW_PROMPT.format(
                outline=outline,
                prev_chapter=prev_chapter,
                prev_summaries=prev_summaries,
                chapter_content=chapter_content,
            ),
            temperature=0.2,
            max_tokens=1200,
        )

    def _generate_text(
        self,
        system_prompt: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        result = self.llm.generate(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not result:
            raise RuntimeError("LLM generation returned empty content")
        return result.strip()

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        clean = re.sub(r"^```json\s*", "", response.strip())
        clean = re.sub(r"\s*```$", "", clean)
        try:
            payload = json.loads(clean)
        except json.JSONDecodeError:
            start = clean.find("{")
            end = clean.rfind("}")
            if start == -1 or end == -1 or start >= end:
                raise ValueError("Unable to parse chapter JSON response")
            payload = json.loads(clean[start : end + 1])

        required = ["title", "summary", "content", "next_chapter_prediction"]
        missing = [item for item in required if item not in payload]
        if missing:
            raise ValueError(f"Chapter JSON missing fields: {', '.join(missing)}")
        return payload

    def _create_json_field_stream_parser(self, field_name: str):
        marker = f'"{field_name}"'
        buffer = ""
        state = "search"
        escape = False

        def consume(chunk: str) -> str:
            nonlocal buffer, state, escape
            buffer += chunk
            emitted: List[str] = []
            index = 0

            while index < len(buffer):
                if state == "search":
                    marker_index = buffer.find(marker, index)
                    if marker_index == -1:
                        keep = max(len(marker) - 1, 0)
                        buffer = buffer[-keep:] if keep else ""
                        index = len(buffer)
                        break
                    index = marker_index + len(marker)
                    state = "colon"
                elif state == "colon":
                    while index < len(buffer) and buffer[index].isspace():
                        index += 1
                    if index >= len(buffer):
                        buffer = buffer[index:]
                        break
                    if buffer[index] != ":":
                        state = "search"
                        continue
                    index += 1
                    state = "before_string"
                elif state == "before_string":
                    while index < len(buffer) and buffer[index].isspace():
                        index += 1
                    if index >= len(buffer):
                        buffer = buffer[index:]
                        break
                    if buffer[index] != '"':
                        state = "search"
                        continue
                    index += 1
                    state = "in_string"
                elif state == "in_string":
                    while index < len(buffer):
                        char = buffer[index]
                        index += 1
                        if escape:
                            escape = False
                            mapping = {
                                '"': '"',
                                "\\": "\\",
                                "/": "/",
                                "b": "\b",
                                "f": "\f",
                                "n": "\n",
                                "r": "\r",
                                "t": "\t",
                            }
                            emitted.append(mapping.get(char, char))
                            continue
                        if char == "\\":
                            escape = True
                            continue
                        if char == '"':
                            state = "done"
                            buffer = buffer[index:]
                            return "".join(emitted)
                        emitted.append(char)
                    buffer = ""
                    return "".join(emitted)
                else:
                    buffer = ""
                    return ""

            return "".join(emitted)

        generator = self._wrap_parser(consume)
        next(generator)
        return generator

    def _wrap_parser(self, func):
        chunk = yield ""
        while True:
            chunk = yield func(chunk)

    def _load_project(self, *, title: str, novel_id: str) -> Dict[str, Any]:
        path = self._project_file(title, novel_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        project = {
            "novel_id": novel_id,
            "title": title,
            "outline_id": None,
            "chapters": [],
            "created_at": self._now_iso(),
            "updated_at": self._now_iso(),
        }
        self._save_project(title, novel_id, project)
        return project

    def _save_project(self, title: str, novel_id: str, project: Dict[str, Any]) -> None:
        path = self._project_file(title, novel_id)
        path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")

    def _touch_project(self, title: str, novel_id: str) -> None:
        project = self._load_project(title=title, novel_id=novel_id)
        project["updated_at"] = self._now_iso()
        self._save_project(title, novel_id, project)

    def _find_chapter(self, project: Dict[str, Any], note_id: str) -> Dict[str, Any]:
        for chapter in project.get("chapters", []):
            if chapter.get("id") == note_id:
                return chapter
        raise FileNotFoundError("Chapter not found")

    def _project_dir(self, title: str, novel_id: str) -> Path:
        safe_title = re.sub(r'[<>:"/\\\\|?*]+', "_", title.strip()) or "untitled"
        safe_novel_id = re.sub(r'[<>:"/\\\\|?*]+', "_", novel_id.strip()) or "default"
        path = self.workspace_root / f"{safe_title}-{safe_novel_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _outline_dir(self, title: str, novel_id: str) -> Path:
        path = self._project_dir(title, novel_id) / "outline"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _chapter_dir(self, title: str, novel_id: str) -> Path:
        path = self._project_dir(title, novel_id) / "chapters"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _project_file(self, title: str, novel_id: str) -> Path:
        return self._project_dir(title, novel_id) / "project_data.json"

    def _next_note_id(self, project: Dict[str, Any], prefix: str) -> str:
        counter = len(project.get("chapters", [])) if prefix == "chapter" else int(bool(project.get("outline_id")))
        return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{counter}"

    def _write_markdown_note(
        self,
        *,
        note_path: Path,
        note_id: str,
        title: str,
        note_type: str,
        tags: List[str],
        content: str,
        created_at: Optional[str] = None,
    ) -> None:
        created = created_at or self._now_iso()
        updated = self._now_iso()
        frontmatter = [
            "---",
            f"id: {note_id}",
            f"title: {title}",
            f"type: {note_type}",
            f"tags: {json.dumps(tags, ensure_ascii=False)}",
            f"created_at: {created}",
            f"updated_at: {updated}",
            "---",
            "",
            f"# {title}",
            "",
            content.strip(),
        ]
        note_path.write_text("\n".join(frontmatter), encoding="utf-8")

    def _read_note(self, note_path: Path) -> Dict[str, Any]:
        if not note_path.exists():
            raise FileNotFoundError(note_path.name)
        text = note_path.read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not match:
            return {"title": note_path.stem, "tags": [], "created_at": self._now_iso()}
        data: Dict[str, Any] = {}
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "tags":
                try:
                    data[key] = json.loads(value)
                except json.JSONDecodeError:
                    data[key] = []
            else:
                data[key] = value
        return data

    def _read_note_body(self, note_path: Path) -> str:
        text = note_path.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) == 3:
                text = parts[2].strip()
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            text = "\n".join(lines[1:]).strip()
        return text.strip()

    def _first_tag(self, note: Dict[str, Any]) -> str:
        tags = note.get("tags", [])
        return str(tags[0]).strip() if tags else ""

    def _format_style_tags(self, style_tags: Optional[Dict[str, str]]) -> str:
        if not style_tags:
            return "无"
        return "\n".join(f"- {key}: {value}" for key, value in style_tags.items())

    def _require_llm(self, action: str) -> None:
        if not self.llm.available:
            raise RuntimeError(f"LLM 未配置，无法{action}")

    def _now_iso(self) -> str:
        return datetime.now().isoformat()
