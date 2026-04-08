from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class WeatherSnapshot:
    city: str
    temperature: float
    description: str
    humidity: int
    wind_speed: float
    temperature_unit: str = "°C"
    wind_unit: str = "级"
    source: str = "demo"

    def summary_lines(self) -> List[str]:
        return [
            f"城市：{self.city}",
            f"温度：{self.temperature}{self.temperature_unit}",
            f"天气状况：{self.description}",
            f"相对湿度：{self.humidity}%",
            f"风力：{self.wind_speed} {self.wind_unit}",
            f"数据来源：{'实时数据' if self.source == 'live' else '模拟数据'}",
        ]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def feels_cold(self) -> bool:
        return self.temperature < 12

    @property
    def feels_hot(self) -> bool:
        return self.temperature >= 28

    @property
    def is_rainy(self) -> bool:
        return any(token in self.description for token in ("雨", "雪", "sleet", "rain", "snow"))

    @property
    def is_windy(self) -> bool:
        return "风" in self.description or self.wind_speed >= 5


@dataclass
class FashionAdviceDraft:
    advice: str
    outfit_summary: List[str]
    highlights: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FashionAdviceResult:
    weather: WeatherSnapshot
    advice: str
    outfit_summary: List[str]
    highlights: List[str]
    workflow_steps: List[Dict[str, Any]] = field(default_factory=list)
    source_project: str = "allen2000-FashionDailyDress"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weather": self.weather.to_dict(),
            "advice": self.advice,
            "outfit_summary": self.outfit_summary,
            "highlights": self.highlights,
            "workflow_steps": self.workflow_steps,
            "source_project": self.source_project,
        }
