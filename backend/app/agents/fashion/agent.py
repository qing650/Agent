from __future__ import annotations

import json
import logging
from typing import Iterator, Optional

from ...core.llm import ChatLLM
from ...storage.config import MemoryConfig
from .models import FashionAdviceDraft, WeatherSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

FASHION_SYSTEM_PROMPT = """\
你是一位有真实审美判断力的专业服饰顾问，擅长将天气数据转化为有温度、有细节的穿搭方案。

## 输出规范
1. 语言：中文。语气专业、直接，不堆砌形容词，不空泛。
2. 结构：
   - 【风格定调】一句话说明整体穿搭气质方向（具体形容，不用"休闲""正式"等泛词）。
   - 【上装】具体款式 + 面料或颜色建议（1-2 条）。
   - 【下装】具体款式 + 搭配逻辑（1-2 条）。
   - 【鞋履】款式 + 若有天气限制需说明原因。
   - 【外层 & 配饰】是否需要、何时穿脱、与整体的协调性。
   - 【注意事项】仅写真正影响舒适或安全的点，不超过 2 条。
3. 禁止输出：泛泛的"适合今天天气"类废话、重复天气数字、过多的感叹句。
4. 若天气存在不确定性或早晚温差大，主动告知分层策略。\
"""

OUTFIT_SUMMARY_SYSTEM_PROMPT = """\
你是一个服装搭配结构提取器。根据输入的天气与场景信息，输出一个 JSON 数组，恰好包含 4 个字符串元素，顺序固定：
[上装建议, 下装建议, 鞋履建议, 外层与配饰建议]

要求：
- 每条建议 15-30 字，具体到款式或面料，不要泛化描述。
- 必须考虑天气（降水、风力、温度）对选材和款式的实际影响。
- 仅输出 JSON 数组，不要任何解释文字、markdown 标记或 key 名。
示例格式：["棉质短袖或薄款防晒衬衫", "浅色直筒休闲裤或亚麻短裤", "网面运动鞋或镂空凉鞋", "防晒帽与 UV 墨镜，备薄外套应对室内冷气"]\
"""

ADVICE_PROMPT_TEMPLATE = """\
请为以下用户生成完整穿搭建议。

## 天气信息
{weather_lines}

## 用户需求
- 场景：{occasion}
- 风格偏好：{style_preference}

## 已生成搭配骨架（供参考，可适当调整）
- 上装：{top}
- 下装：{bottom}
- 鞋履：{shoes}
- 外层与配饰：{outer}

请按系统提示中的结构输出完整建议。\
"""

OUTFIT_SUMMARY_PROMPT_TEMPLATE = """\
## 天气
{weather_lines}

## 场景
{occasion}

## 风格偏好
{style_preference}

请输出 4 元素 JSON 数组。\
"""


class FashionAgent:
    """Generates fashion guidance from an upstream weather snapshot.

    All outfit recommendations are generated dynamically by the LLM;
    no hard-coded clothing strings exist in this class.
    """

    def __init__(self, config: Optional[MemoryConfig] = None, llm: Optional[ChatLLM] = None):
        self.config = config or MemoryConfig()
        self.llm = llm or ChatLLM()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def advise(
        self,
        *,
        weather: WeatherSnapshot,
        occasion: Optional[str] = None,
        style_preference: Optional[str] = None,
    ) -> FashionAdviceDraft:
        outfit_summary = self._build_outfit_summary(weather, occasion=occasion, style_preference=style_preference)
        highlights = self._build_highlights(weather, occasion=occasion, style_preference=style_preference)
        advice = self._generate_advice(
            weather,
            outfit_summary=outfit_summary,
            occasion=occasion,
            style_preference=style_preference,
        )
        return FashionAdviceDraft(
            advice=advice,
            outfit_summary=outfit_summary,
            highlights=highlights,
        )

    def stream_advice(
        self,
        *,
        weather: WeatherSnapshot,
        outfit_summary: list[str],
        occasion: Optional[str],
        style_preference: Optional[str],
    ) -> Iterator[str]:
        prompt = self._render_advice_prompt(
            weather,
            outfit_summary=outfit_summary,
            occasion=occasion,
            style_preference=style_preference,
        )
        yield from self.llm.stream_generate(
            FASHION_SYSTEM_PROMPT,
            [{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1200,
        )

    # ------------------------------------------------------------------
    # Internal generation helpers
    # ------------------------------------------------------------------

    def _generate_advice(
        self,
        weather: WeatherSnapshot,
        *,
        outfit_summary: list[str],
        occasion: Optional[str],
        style_preference: Optional[str],
    ) -> str:
        prompt = self._render_advice_prompt(
            weather,
            outfit_summary=outfit_summary,
            occasion=occasion,
            style_preference=style_preference,
        )
        result = self.llm.generate(
            FASHION_SYSTEM_PROMPT,
            [{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1200,
        )
        if result:
            return result
        logger.warning("LLM returned empty advice; using fallback for city=%s", weather.city)
        return self._fallback_advice(weather, outfit_summary, occasion=occasion, style_preference=style_preference)

    def _build_outfit_summary(
        self,
        weather: WeatherSnapshot,
        *,
        occasion: Optional[str],
        style_preference: Optional[str],
    ) -> list[str]:
        """Ask the LLM to produce a 4-element outfit skeleton; fall back gracefully."""
        prompt = OUTFIT_SUMMARY_PROMPT_TEMPLATE.format(
            weather_lines="\n".join(weather.summary_lines()),
            occasion=occasion or "通勤 / 日常",
            style_preference=style_preference or "简洁实穿",
        )
        raw = self.llm.generate(
            OUTFIT_SUMMARY_SYSTEM_PROMPT,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        if raw:
            parsed = self._parse_outfit_json(raw)
            if parsed:
                return parsed
        logger.warning("Outfit summary LLM call failed or returned bad JSON; using minimal fallback.")
        return self._minimal_outfit_fallback(weather)

    def _parse_outfit_json(self, raw: str) -> list[str] | None:
        """Extract a 4-element string list from the LLM output."""
        try:
            # Strip markdown fences if present
            text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(text)
            if isinstance(data, list) and len(data) == 4 and all(isinstance(s, str) for s in data):
                return data
        except Exception as exc:
            logger.debug("Outfit JSON parse failed: %s | raw=%r", exc, raw)
        return None

    def _minimal_outfit_fallback(self, weather: WeatherSnapshot) -> list[str]:
        """Absolute last-resort fallback: four generic but weather-aware strings."""
        temp = weather.temperature
        rain_note = "，选防水款式" if weather.is_rainy else ""
        wind_note = "，选防风面料" if weather.is_windy else ""

        if weather.feels_hot:
            return [
                f"透气短袖或薄款衬衫{wind_note}",
                "轻薄长裤或短裤",
                f"网面运动鞋或凉鞋{rain_note}",
                "防晒层与遮阳帽",
            ]
        if weather.feels_cold:
            return [
                f"保暖打底叠穿毛衣或厚卫衣{wind_note}",
                "厚长裤或保暖裤",
                f"短靴或保暖运动鞋{rain_note}",
                "大衣或羽绒服，围巾手套按需",
            ]
        return [
            f"长袖衬衫或薄针织{wind_note}",
            "休闲长裤或牛仔裤",
            f"运动鞋或轻便皮鞋{rain_note}",
            "备一件轻外套应对早晚温差",
        ]

    # ------------------------------------------------------------------
    # Prompt rendering
    # ------------------------------------------------------------------

    def _render_advice_prompt(
        self,
        weather: WeatherSnapshot,
        *,
        outfit_summary: list[str],
        occasion: Optional[str],
        style_preference: Optional[str],
    ) -> str:
        top, bottom, shoes, outer = (outfit_summary + [""] * 4)[:4]
        return ADVICE_PROMPT_TEMPLATE.format(
            weather_lines="\n".join(weather.summary_lines()),
            occasion=occasion or "通勤 / 日常",
            style_preference=style_preference or "简洁实穿",
            top=top,
            bottom=bottom,
            shoes=shoes,
            outer=outer,
        )

    def _fallback_advice(
        self,
        weather: WeatherSnapshot,
        outfit_summary: list[str],
        *,
        occasion: Optional[str],
        style_preference: Optional[str],
    ) -> str:
        top, bottom, shoes, outer = (outfit_summary + ["（待定）"] * 4)[:4]
        scene = occasion or "日常出行"
        style = style_preference or "简洁实穿"
        caution = self._weather_caution(weather)
        return (
            f"【风格定调】{weather.city} 当日适合走 {style} 路线，优先兼顾 {scene} 的舒适度与机动性。\n"
            f"【上装】{top}\n"
            f"【下装】{bottom}\n"
            f"【鞋履】{shoes}\n"
            f"【外层 & 配饰】{outer}\n"
            f"【注意事项】当前 {weather.temperature}{weather.temperature_unit}，{caution}"
        )

    # ------------------------------------------------------------------
    # Highlights & caution
    # ------------------------------------------------------------------

    def _build_highlights(
        self,
        weather: WeatherSnapshot,
        *,
        occasion: Optional[str],
        style_preference: Optional[str],
    ) -> list[str]:
        highlights = [
            "协作链路：WeatherAgent → FashionAgent → FashionCoordinatorAgent",
            f"城市 {weather.city} 使用{'实时' if weather.source == 'live' else '模拟'}天气数据",
            f"适配场景：{occasion or '日常'}",
        ]
        if style_preference:
            highlights.append(f"风格锚点：{style_preference}")
        highlights.append(self._weather_caution(weather))
        return highlights

    def _weather_caution(self, weather: WeatherSnapshot) -> str:
        if weather.is_rainy and "雪" in weather.description:
            return "路面可能湿滑，鞋底抓地力优先于造型选择。"
        if weather.is_rainy:
            return "有降水，优先选耐湿面料；备用袜子可避免一天的不适。"
        if weather.temperature >= 33:
            return "高温注意补水与防晒，深色厚重材质会明显加重热感。"
        if weather.temperature <= 5:
            return "分层穿搭比单件厚穿更易应对室内外温差，方便随时调节。"
        if weather.is_windy:
            return "风感明显，外层建议有收口设计或防风面料，避免下摆过宽。"
        return "早晚温差可能明显，建议保留一件可随时增减的外层。"
