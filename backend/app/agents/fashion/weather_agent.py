from __future__ import annotations

import json
import logging
import os
import random
import re
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from .models import WeatherSnapshot

logger = logging.getLogger(__name__)


CITY_ALIASES: dict[str, str] = {
    "beijing": "北京",
    "shanghai": "上海",
    "guangzhou": "广州",
    "shenzhen": "深圳",
    "hangzhou": "杭州",
    "nanjing": "南京",
    "suzhou": "苏州",
    "chengdu": "成都",
    "wuhan": "武汉",
    "xian": "西安",
    "xi'an": "西安",
    "chongqing": "重庆",
    "tianjin": "天津",
    "tokyo": "东京",
    "osaka": "大阪",
    "seoul": "首尔",
    "singapore": "新加坡",
    "hong kong": "香港",
}

# Climatologically plausible temperature bands for seeded demo generation.
# (min_temp, max_temp) in °C — intentionally broad to cover all seasons.
_TEMP_BAND = (8.0, 32.0)


class WeatherAgent:
    """Fetches live weather from AMap and falls back to deterministic demo data.

    Demo weather descriptions are derived from the simulated temperature and
    humidity rather than selected from a pre-defined list, so the fallback path
    remains expressive without embedding any fixed string catalogue.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.weather_api_key = api_key or os.getenv("AMAP_API_KEY") or os.getenv("OPENWEATHER_API_KEY")

    def get_weather(self, city: str) -> WeatherSnapshot:
        city_name = city.strip() or "上海"
        live = self._fetch_live_weather(city_name)
        if live is None:
            logger.warning("Falling back to demo weather for city=%s", city_name)
        return live or self._demo_weather(city_name)

    # ------------------------------------------------------------------
    # Live weather (AMap)
    # ------------------------------------------------------------------

    def _fetch_live_weather(self, city: str) -> Optional[WeatherSnapshot]:
        if not self.weather_api_key:
            logger.info("AMap API key not configured; using demo weather for city=%s", city)
            return None

        normalized = self._normalize_city(city)
        city_code = self._resolve_city_code(normalized)
        if not city_code:
            logger.warning("Failed to resolve AMap city code for city=%s", city)
            return None

        endpoint = (
            "https://restapi.amap.com/v3/weather/weatherInfo"
            f"?key={self.weather_api_key}&city={quote(city_code)}&extensions=base&output=JSON"
        )
        logger.info("Requesting AMap live weather city=%s code=%s", city, city_code)

        payload = self._request_json(endpoint, context=f"AMap weather city={city}")
        if not payload:
            return None

        try:
            if payload.get("status") != "1":
                logger.warning(
                    "AMap weather non-success: city=%s infocode=%s info=%s",
                    city, payload.get("infocode"), payload.get("info"),
                )
                return None

            lives = payload.get("lives") or []
            if not lives:
                logger.warning("AMap weather empty lives: city=%s", city)
                return None

            live = lives[0]
            return WeatherSnapshot(
                city=live.get("city") or normalized or city,
                temperature=round(float(live["temperature"]), 1),
                description=str(live.get("weather") or "未知"),
                humidity=self._parse_humidity(live.get("humidity")),
                wind_speed=self._parse_wind_power(live.get("windpower")),
                temperature_unit="°C",
                wind_unit="级",
                source="live",
            )
        except Exception as exc:
            logger.exception("Failed to parse AMap weather payload: city=%s error=%s", city, exc)
            return None

    def _resolve_city_code(self, city: str) -> Optional[str]:
        if city.isdigit():
            return city

        endpoint = (
            "https://restapi.amap.com/v3/geocode/geo"
            f"?key={self.weather_api_key}&address={quote(city)}&output=JSON"
        )
        payload = self._request_json(endpoint, context=f"AMap geocode city={city}")
        if not payload:
            return None

        try:
            if payload.get("status") != "1":
                logger.warning(
                    "AMap geocode non-success: city=%s infocode=%s info=%s",
                    city, payload.get("infocode"), payload.get("info"),
                )
                return None

            geocodes = payload.get("geocodes") or []
            if not geocodes:
                logger.warning("AMap geocode empty result: city=%s", city)
                return None

            return geocodes[0].get("adcode")
        except Exception as exc:
            logger.exception("Failed to parse AMap geocode payload: city=%s error=%s", city, exc)
            return None

    def _request_json(self, endpoint: str, *, context: str) -> Optional[dict]:
        try:
            with urlopen(endpoint, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            logger.warning("%s HTTP error: status=%s reason=%s body=%s", context, exc.code, exc.reason, body or "<empty>")
        except URLError as exc:
            logger.warning("%s network error: reason=%s", context, exc.reason)
        except Exception as exc:
            logger.exception("%s unexpected error: %s", context, exc)
        return None

    # ------------------------------------------------------------------
    # Demo weather (no pre-defined description list)
    # ------------------------------------------------------------------

    def _demo_weather(self, city: str) -> WeatherSnapshot:
        """Generate deterministic but realistic demo weather from the city name.

        Description is derived from computed temperature and humidity values,
        not selected from a hard-coded catalogue.
        """
        seed = sum(ord(c) for c in city.lower())
        rng = random.Random(seed)

        temp_min, temp_max = _TEMP_BAND
        temperature = round(temp_min + rng.random() * (temp_max - temp_min), 1)
        humidity = 40 + (seed % 50)          # 40–89 %
        wind_speed = round(1 + rng.random() * 5, 1)   # 1–6 级

        description = self._derive_description(temperature, humidity, wind_speed, rng)

        return WeatherSnapshot(
            city=city,
            temperature=temperature,
            description=description,
            humidity=humidity,
            wind_speed=wind_speed,
            temperature_unit="°C",
            wind_unit="级",
            source="demo",
        )

    @staticmethod
    def _derive_description(temp: float, humidity: int, wind: float, rng: random.Random) -> str:
        """Compose a weather description string from numeric indicators.

        Rules are deterministic given the same inputs, avoiding any stored list.
        """
        # Precipitation signal: high humidity + lower temperature bias
        precip_score = (humidity - 55) / 45 + (20 - temp) / 30   # rough score
        if precip_score > 0.9:
            precip = "大雨" if humidity > 85 else "中雨"
        elif precip_score > 0.5:
            precip = "小雨"
        elif precip_score > 0.2 and rng.random() < 0.4:
            precip = "阵雨"
        else:
            precip = ""

        if not precip and temp <= 2 and humidity >= 70:
            precip = "小雪"

        # Cloud / sun signal
        if precip:
            sky = "阴"
        elif humidity > 70:
            sky = "多云" if rng.random() < 0.6 else "晴间多云"
        elif humidity > 50:
            sky = "晴间多云" if rng.random() < 0.5 else "晴朗"
        else:
            sky = "晴朗"

        # Wind suffix
        wind_suffix = "，有风" if wind >= 4 else ""

        if precip:
            return f"{sky}{precip}{wind_suffix}".strip("，")
        return f"{sky}{wind_suffix}".strip("，")

    # ------------------------------------------------------------------
    # Parsing utilities
    # ------------------------------------------------------------------

    def _normalize_city(self, city: str) -> str:
        return CITY_ALIASES.get(city.strip().lower(), city.strip())

    def _parse_humidity(self, humidity: object) -> int:
        text = str(humidity or "").replace("%", "").strip()
        if not text:
            return 50
        try:
            value = int(float(text))
            return value if 0 <= value <= 100 else 50
        except (ValueError, TypeError) as exc:
            logger.warning("Failed to parse humidity %r: %s", humidity, exc)
            return 50

    def _parse_wind_power(self, wind_power: object) -> float:
        text = (
            str(wind_power or "")
            .strip()
            .replace("级", "")
            .replace("≤", "")
            .replace("＜", "")
            .replace("<=", "")
            .replace(">=", "")
            .replace("≥", "")
            .replace("＞", "")
            .replace("<", "")
            .replace(">", "")
            .strip()
        )
        numbers = re.findall(r"\d+(?:\.\d+)?", text)
        if not numbers:
            logger.warning("Unexpected windpower format: %r", wind_power)
            return 0.0
        values = [float(n) for n in numbers]
        return round(sum(values) / len(values), 1)
