from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, Optional

from .agent import FashionAgent
from .models import FashionAdviceResult, WeatherSnapshot
from .weather_agent import WeatherAgent

logger = logging.getLogger(__name__)


class FashionCoordinatorAgent:
    """Coordinates weather retrieval and fashion recommendation into one response."""

    def __init__(
        self,
        weather_agent: Optional[WeatherAgent] = None,
        fashion_agent: Optional[FashionAgent] = None,
    ):
        self.weather_agent = weather_agent or WeatherAgent()
        self.fashion_agent = fashion_agent or FashionAgent()

    # ------------------------------------------------------------------
    # Synchronous path
    # ------------------------------------------------------------------

    def advise(
        self,
        *,
        city: str,
        occasion: Optional[str] = None,
        style_preference: Optional[str] = None,
    ) -> FashionAdviceResult:
        weather = self.weather_agent.get_weather(city)
        draft = self.fashion_agent.advise(
            weather=weather,
            occasion=occasion,
            style_preference=style_preference,
        )
        workflow_steps = self._build_workflow_steps(
            weather=weather,
            outfit_summary=draft.outfit_summary,
            occasion=occasion,
            style_preference=style_preference,
        )
        return FashionAdviceResult(
            weather=weather,
            advice=draft.advice,
            outfit_summary=draft.outfit_summary,
            highlights=draft.highlights,
            workflow_steps=workflow_steps,
        )

    # ------------------------------------------------------------------
    # Streaming path
    # ------------------------------------------------------------------

    def stream_advise(
        self,
        *,
        city: str,
        occasion: Optional[str] = None,
        style_preference: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        weather = self.weather_agent.get_weather(city)
        outfit_summary = self.fashion_agent._build_outfit_summary(
            weather,
            occasion=occasion,
            style_preference=style_preference,
        )
        highlights = self.fashion_agent._build_highlights(
            weather,
            occasion=occasion,
            style_preference=style_preference,
        )
        workflow_steps = self._build_workflow_steps(
            weather=weather,
            outfit_summary=outfit_summary,
            occasion=occasion,
            style_preference=style_preference,
        )

        yield {
            "type": "meta",
            "data": {
                "weather": weather.to_dict(),
                "outfit_summary": outfit_summary,
                "highlights": highlights,
                "workflow_steps": workflow_steps,
            },
        }

        parts: list[str] = []
        for chunk in self.fashion_agent.stream_advice(
            weather=weather,
            outfit_summary=outfit_summary,
            occasion=occasion,
            style_preference=style_preference,
        ):
            parts.append(chunk)
            yield {"type": "content", "data": chunk}

        advice = "".join(parts).strip()
        if not advice:
            logger.warning(
                "Fashion streaming produced no content; falling back to non-stream for city=%s", city
            )
            advice = self.fashion_agent._generate_advice(
                weather,
                outfit_summary=outfit_summary,
                occasion=occasion,
                style_preference=style_preference,
            )
            if advice:
                yield {"type": "content", "data": advice}

        result = FashionAdviceResult(
            weather=weather,
            advice=advice,
            outfit_summary=outfit_summary,
            highlights=highlights,
            workflow_steps=workflow_steps,
        )
        yield {"type": "done", "data": result.to_dict()}

    # ------------------------------------------------------------------
    # Workflow metadata
    # ------------------------------------------------------------------

    def _build_workflow_steps(
        self,
        *,
        weather: WeatherSnapshot,
        outfit_summary: list[str],
        occasion: Optional[str],
        style_preference: Optional[str],
    ) -> list[Dict[str, str]]:
        scene = occasion or "日常"
        style = style_preference or "简洁实穿"
        weather_note = (
            f"{weather.city} {weather.temperature}{weather.temperature_unit}，"
            f"{weather.description}，湿度 {weather.humidity}%，风力 {weather.wind_speed} {weather.wind_unit}"
        )
        outfit_note = " / ".join(outfit_summary) if outfit_summary else "（生成中）"

        return [
            {
                "step": "Step 01",
                "title": "天气获取",
                "input": f"城市：{weather.city}",
                "output": weather_note,
            },
            {
                "step": "Step 02",
                "title": "穿搭骨架生成",
                "input": f"天气数据 + 场景：{scene} + 风格：{style}",
                "output": outfit_note,
            },
            {
                "step": "Step 03",
                "title": "完整建议生成",
                "input": "天气快照 + 穿搭骨架 + 用户偏好",
                "output": "结构化穿搭建议（风格定调、上下装、鞋履、外层配饰、注意事项）",
            },
            {
                "step": "Step 04",
                "title": "协调器整合",
                "input": "天气快照 + 穿搭草稿",
                "output": "组装 FashionAdviceResult，附元数据与工作流摘要",
            },
        ]
