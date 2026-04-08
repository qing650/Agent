from __future__ import annotations

import math
import os
import re
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        raise NotImplementedError

    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embedding fallback."""

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in self._tokenize(text):
            idx = hash(token) % self.dimensions
            sign = -1.0 if (hash(f"{token}:sign") % 2) else 1.0
            vector[idx] += sign
        return self._normalize(vector)

    def _tokenize(self, text: str) -> List[str]:
        normalized = (text or "").lower()
        tokens = re.findall(r"[\u4e00-\u9fff]|[a-z0-9_]+", normalized)
        return tokens or [normalized[:100]]

    def _normalize(self, vector: List[float]) -> List[float]:
        length = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / length for value in vector]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None):
        from openai import OpenAI

        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url or os.getenv("OPENAI_BASE_URL"))

    def embed(self, text: str) -> List[float]:
        result = self.client.embeddings.create(model=self.model, input=text)
        return list(result.data[0].embedding)

    def embed_batch(self, texts: Iterable[str]) -> List[List[float]]:
        text_list = list(texts)
        if not text_list:
            return []
        result = self.client.embeddings.create(model=self.model, input=text_list)
        return [list(item.embedding) for item in result.data]


def create_embedding_provider(provider: str = "auto", model: str = "text-embedding-3-small", dimensions: int = 256) -> EmbeddingProvider:
    provider_name = (provider or "auto").lower()
    
    if provider_name in {"hash", "local"}:
        return HashEmbeddingProvider(dimensions=dimensions)
    
    if provider_name in {"openai", "auto"}:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
        
        # 如果用的是非 OpenAI API (如 DashScope)，不要尝试 OpenAI embedding
        if base_url and "openai" not in base_url.lower():
            return HashEmbeddingProvider(dimensions=dimensions)
        
        if api_key:
            try:
                return OpenAIEmbeddingProvider(
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                )
            except Exception:
                pass
    
    return HashEmbeddingProvider(dimensions=dimensions)
