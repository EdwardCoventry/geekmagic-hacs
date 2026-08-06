"""Weather widget for GeekMagic displays."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import mdi_span
from ._card import card_html, chip_html
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


WEATHER_ICONS = {
    "sunny": "weather-sunny",
    "clear-night": "weather-night",
    "partlycloudy": "weather-partly-cloudy",
    "cloudy": "weather-cloudy",
    "rainy": "weather-rainy",
    "pouring": "weather-pouring",
    "snowy": "weather-snowy",
    "snowy-rainy": "weather-snowy-rainy",
    "fog": "weather-fog",
    "hail": "weather-hail",
    "windy": "weather-windy",
    "windy-variant": "weather-windy-variant",
    "lightning": "weather-lightning",
    "lightning-rainy": "weather-lightning-rainy",
    "exceptional": "alert-circle",
}

# Condition → theme palette CSS variable. Each weather condition resolves
# to a role on the active theme so candy/retro/neon/etc. show tints from
# their own palette, not hardcoded watchOS-system colors.
#
# Mapping rationale:
#   sunny / hot      → warning  (orange-ish on most themes)
#   clear-night      → secondary
#   cloudy / partly  → primary  (uses the theme's brand accent)
#   rain / snow / hail → info   (cool/water/data role — themes that
#                                 lack blue map this to mint/cyan/etc.)
#   wind             → success
#   lightning        → secondary
#   exceptional      → error
#   fog              → muted
WEATHER_COLORS: dict[str, str] = {
    "sunny": "var(--warning)",
    "clear-night": "var(--secondary)",
    "partlycloudy": "var(--primary)",
    "cloudy": "var(--primary)",
    "rainy": "var(--info)",
    "pouring": "var(--info)",
    "snowy": "var(--info)",
    "snowy-rainy": "var(--info)",
    "fog": "var(--muted)",
    "hail": "var(--info)",
    "windy": "var(--success)",
    "windy-variant": "var(--success)",
    "lightning": "var(--secondary)",
    "lightning-rainy": "var(--secondary)",
    "exceptional": "var(--error)",
}


# Weekday abbreviations
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse_forecast_day_name(datetime_str: str, fallback: str) -> str:
    """Parse datetime string and return weekday abbreviation.

    Args:
        datetime_str: ISO format datetime string (e.g., "2025-12-29T00:00:00+00:00")
        fallback: Fallback string if parsing fails

    Returns:
        Weekday abbreviation (Mon, Tue, etc.) or fallback
    """
    if not datetime_str:
        return fallback

    try:
        # Try parsing ISO format (with or without timezone)
        # Remove timezone suffix for simpler parsing
        dt_str = datetime_str.split("+", 1)[0].split("Z", 1)[0]
        dt = datetime.fromisoformat(dt_str)
        return WEEKDAY_NAMES[dt.weekday()]
    except (ValueError, IndexError):
        # If parsing fails, try to use first 3 chars as fallback
        # (might be already a day name like "Mon")
        if len(datetime_str) >= 3 and datetime_str[:3].isalpha():
            return datetime_str[:3]
        return fallback


def _fmt_num(value: Any) -> Any:
    """Round a number to a whole integer for compact secondary display.

    Forecast temps, hi/lo chips and humidity show no decimals at all
    (``22.6`` -> ``23``, ``14.0`` -> ``14``); non-numbers (``"--"``,
    ``None``) pass through untouched. The hero/top temperature keeps its
    full precision and never goes through this helper.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(value)
    return value


def _temp_str(value: Any) -> str:
    """Format a temperature value as ``"22°"`` (or ``"--"`` when missing)."""
    if value is None or value == "--":
        return "--"
    return f"{value}°"


def _condition_label(condition: str) -> str:
    """Human-readable condition label ("partlycloudy" → "Partly Cloudy")."""
    if condition == "partlycloudy":
        return "Partly Cloudy"
    return condition.replace("-", " ").title()


def _tinted_chip(text: str, icon: str, icon_color: str) -> str:
    """A chip whose icon carries a semantic tint while the text stays neutral.

    ``chip_html``'s ``color`` tints the whole chip; hi/lo chips want only
    the ↑/↓ arrow tinted (warning/info) with secondary text.
    """
    icon_html = mdi_span(icon, "icon", f"color: {icon_color}")
    return f'<span class="chip">{icon_html}<span>{escape(text)}</span></span>'


def _weather_placeholder() -> str:
    """Placeholder fragment when no weather data is available."""
    icon = mdi_span("weather-cloudy", "icon i-md", "color: var(--text-secondary)")
    return f'<div class="cell">{icon}<div class="t-label hide-short">NO WEATHER DATA</div></div>'


class WeatherWidget(Widget):
    """Widget that displays weather information.

    Three-band card plus a forecast strip:
      icon   = condition icon (feature band, condition-tinted)
      hero   = current temperature (full precision)
      chips  = condition text, today's ↑hi ↓lo, humidity
      extra  = forecast strip (flex row of DAY / icon / hi°/lo° mini
               columns), hidden in small cells via ``.hide-small``.
    """

    WIDGET_TYPE: ClassVar[str] = "weather"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Weather",
        "needs_entity": True,
        "entity_domains": ["weather"],
        "options": [
            {"key": "show_forecast", "type": "boolean", "label": "Show Forecast", "default": True},
            {
                "key": "forecast_days",
                "type": "number",
                "label": "Forecast Days",
                "default": 3,
                "min": 1,
                "max": 5,
            },
            {
                "key": "forecast_start_tomorrow",
                "type": "boolean",
                "label": "Forecast Starts Tomorrow",
                "default": False,
            },
            {"key": "show_humidity", "type": "boolean", "label": "Show Humidity", "default": True},
            {"key": "show_high_low", "type": "boolean", "label": "Show High/Low", "default": True},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the weather widget."""
        super().__init__(config)
        self.show_forecast = config.options.get("show_forecast", True)
        self.forecast_days = config.options.get("forecast_days", 3)
        self.forecast_start_tomorrow = config.options.get("forecast_start_tomorrow", False)
        self.show_humidity = config.options.get("show_humidity", True)
        self.show_high_low = config.options.get("show_high_low", True)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _visible_forecast(self, forecast: list[dict]) -> list[dict]:
        """Return the forecast entries to display.

        Daily forecasts include today as the first entry. When
        ``forecast_start_tomorrow`` is set we drop it so the strip begins
        at tomorrow instead.
        """
        items = forecast[1:] if self.forecast_start_tomorrow else forecast
        return items[: self.forecast_days]

    @staticmethod
    def _today_high_low(forecast: list[dict]) -> tuple[Any, Any]:
        """Return ``(high, low)`` from the first forecast day, if available."""
        if not forecast:
            return (None, None)
        day = forecast[0]
        return (day.get("temperature"), day.get("templow"))

    # ------------------------------------------------------------------
    # Fragment builders
    # ------------------------------------------------------------------

    def _forecast_column(self, day: dict, index: int, high_only: bool) -> str:
        """One mini forecast column: ``DAY`` / icon / ``hi°/lo°`` (or ``hi°``)."""
        day_condition = day.get("condition", "sunny")
        day_icon = WEATHER_ICONS.get(day_condition, "weather-sunny")
        day_tint = WEATHER_COLORS.get(day_condition, "var(--warning)")
        day_temp = day.get("temperature", "--")
        day_low = day.get("templow")
        day_name = _parse_forecast_day_name(day.get("datetime", ""), f"D{index + 1}")

        hi_html = escape(_temp_str(_fmt_num(day_temp)))
        if self.show_high_low and not high_only and day_low is not None:
            lo_html = escape(_temp_str(_fmt_num(day_low)))
            temp_html = f'{hi_html}<span style="color: var(--text-tertiary)">/{lo_html}</span>'
        else:
            temp_html = hi_html

        return (
            '<div style="display: flex; flex-direction: column; align-items: center; '
            'gap: 2%; min-width: 0">'
            f'<div class="t-label">{escape(day_name.upper())}</div>'
            f"{mdi_span(day_icon, 'icon i-sm', f'color: {day_tint}')}"
            '<div style="font-size: clamp(10px, 9vmin, 17px); font-weight: 700; '
            f'line-height: 1">{temp_html}</div>'
            "</div>"
        )

    def _forecast_strip(self, ctx: CellContext, forecast: list[dict]) -> str:
        """Flex row of forecast mini columns, or ``""`` when not shown.

        Hidden via ``.hide-small`` in cells under 130px; the day count and
        hi/lo verbosity also adapt to the cell width so columns never
        collide in mid-size cells.
        """
        if not self.show_forecast:
            return ""
        items = self._visible_forecast(forecast)
        if not items:
            return ""

        # Width-adaptive density: full-width cells fit every requested
        # day; mid-size cells cap at three columns. Hi/lo pairs only fit
        # up to three columns — four or five days drop to hi-only so the
        # temps don't collide.
        if ctx.width < 200:
            items = items[:3]
        high_only = ctx.width < 200 or len(items) > 3

        columns = "".join(self._forecast_column(day, i, high_only) for i, day in enumerate(items))
        return (
            '<div class="hide-small" style="display: flex; width: 100%; '
            'align-items: center; justify-content: space-evenly">'
            f"{columns}</div>"
        )

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the weather widget."""
        entity = state.entity
        if entity is None:
            return _weather_placeholder()

        condition = entity.state
        icon_name = WEATHER_ICONS.get(condition, "weather-sunny")
        icon_tint = WEATHER_COLORS.get(condition, "var(--warning)")
        temperature = entity.get("temperature", "--")
        humidity = entity.get("humidity", "--")

        # Meta chips: today's hi/lo + humidity — caption-tier metadata
        # about the hero, auto-hidden in small cells. The condition text
        # lives in the caption band so this single row never overflows.
        chips: list[str] = []
        if self.show_high_low:
            high, low = self._today_high_low(state.forecast)
            if high is not None:
                chips.append(_tinted_chip(f"{_fmt_num(high)}°", "arrow-up-thin", "var(--warning)"))
            if low is not None:
                chips.append(_tinted_chip(f"{_fmt_num(low)}°", "arrow-down-thin", "var(--info)"))
        # The chip strip is only visible in cells >= 130px wide; below
        # ~180px the hi/lo pair plus humidity would still overflow, so
        # keep humidity for roomy cells only (matches the old layouts,
        # which showed humidity in wide cells).
        if self.show_humidity and humidity != "--" and ctx.width >= 180:
            chips.append(
                chip_html(f"{_fmt_num(humidity)}%", icon="water-percent", color="var(--info)")
            )

        return card_html(
            caption=_condition_label(condition),
            icon=icon_name,
            icon_color=icon_tint,
            icon_role="feature",
            hero=_temp_str(temperature),
            chips=chips or None,
            extra=self._forecast_strip(ctx, state.forecast),
        )
