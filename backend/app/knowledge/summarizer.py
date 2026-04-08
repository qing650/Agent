from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MemorySummary:
    facts: List[str]
    summary: str


class MemorySummarizer:
    """Heuristic long-term memory extractor."""

    explicit_patterns = [
        re.compile(r"(?:\u8bf7|\u9ebb\u70e6)?\u8bb0\u4f4f[:\uff1a]?\s*(.+)$"),
        re.compile(r"\u6211\u53eb(.+)$"),
        re.compile(r"\u6211\u7684\u540d\u5b57\u662f(.+)$"),
        re.compile(r"\u6211\u662f(.+)$"),
        re.compile(r"\u6211\u559c\u6b22(.+)$"),
        re.compile(r"\u6211\u4e0d\u559c\u6b22(.+)$"),
        re.compile(r"\u6211\u4e60\u60ef(.+)$"),
        re.compile(r"\u6211\u7684\u76ee\u6807\u662f(.+)$"),
    ]

    def extract_memories(self, messages: List[Dict[str, str]]) -> MemorySummary:
        facts: List[str] = []
        for message in messages:
            if message.get("role") != "user":
                continue
            text = (message.get("content") or "").strip()
            if not text:
                continue
            fact = self._extract_fact_from_text(text)
            if fact and fact not in facts:
                facts.append(fact)
        summary = self._summarize_messages(messages)
        return MemorySummary(facts=facts, summary=summary)

    def _extract_fact_from_text(self, text: str) -> Optional[str]:
        for pattern in self.explicit_patterns:
            match = pattern.search(text)
            if not match:
                continue
            raw = match.group(1).strip("\u3002\uFF1B;\uFF0C, ")
            if 1 <= len(raw) <= 120:
                if pattern.pattern.startswith(r"(?:\u8bf7|\u9ebb\u70e6)?\u8bb0\u4f4f"):
                    return raw
                return f"user_profile: {raw}"
        return None

    def _summarize_messages(self, messages: List[Dict[str, str]], max_items: int = 5) -> str:
        relevant = []
        for message in messages[-max_items * 2 :]:
            content = (message.get("content") or "").strip()
            if not content:
                continue
            prefix = "user" if message.get("role") == "user" else "assistant"
            relevant.append(f"- {prefix}: {content[:160]}")
        return "\n".join(relevant)
