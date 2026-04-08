from __future__ import annotations

import logging
import os
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


class ChatLLM:
    """Thin OpenAI-compatible chat wrapper with graceful fallback."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.2,
    ):
        self.model = model or os.getenv("LLM_MODEL") or os.getenv("LLM_MODEL_ID")
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        self.temperature = temperature
        self._client = None

        if self.model and self.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                logger.info(f"LLM initialized: model={self.model}, base_url={self.base_url or 'default'}")
            except ImportError as e:
                logger.warning(f"OpenAI library not available: {e}")
                self._client = None
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")
                self._client = None
        else:
            missing = []
            if not self.model:
                missing.append("model")
            if not self.api_key:
                missing.append("api_key")
            logger.debug(f"LLM not initialized: missing {', '.join(missing)}")

    @property
    def available(self) -> bool:
        """Check if LLM is available for use."""
        return self._client is not None and bool(self.model) and bool(self.api_key)

    def generate(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Generate response from LLM."""
        if not self.available:
            logger.debug("LLM unavailable - skipping generation")
            return None

        try:
            logger.debug(f"LLM.generate() called with {len(messages)} messages, max_tokens={max_tokens}")

            kwargs = {
                "model": self.model,
                "messages": [{"role": "system", "content": system_prompt}, *messages],
                "temperature": temperature if temperature is not None else self.temperature,
                "stream": False,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            logger.debug(f"OpenAI API call: model={self.model}, base_url={self.base_url}")
            response = self._client.chat.completions.create(**kwargs)
            result = (response.choices[0].message.content or "").strip()
            logger.info(f"LLM generation successful ({len(result)} chars)")
            return result
        except Exception as e:
            logger.error(f"LLM generation failed: {type(e).__name__}: {e}", exc_info=True)
            return None

    def stream_generate(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Iterator[str]:
        """Stream response chunks from the LLM when the backend supports it."""
        if not self.available:
            logger.debug("LLM unavailable - skipping streaming generation")
            return

        try:
            kwargs = {
                "model": self.model,
                "messages": [{"role": "system", "content": system_prompt}, *messages],
                "temperature": temperature if temperature is not None else self.temperature,
                "stream": True,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            logger.debug(f"OpenAI streaming API call: model={self.model}, base_url={self.base_url}")
            stream = self._client.chat.completions.create(**kwargs)
            for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    yield content
        except Exception as e:
            logger.error(f"LLM streaming generation failed: {type(e).__name__}: {e}", exc_info=True)
            return
