"""Weather widget for GeekMagic displays."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import mdi_span
from ._cardfit import (
    HERO_SHARE_STACKED,
    caption_visible,
    cell_box,
    chip_band_px,
    fit_caption,
    fit_hero,
    hero_block,
    label_px,
)
from ._textfit import LABEL_TRACKING, metrics_for
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

# The forecast strip needs a column per day plus legible numerals; below
# this width the columns collide, so the strip drops out entirely.
_STRIP_MIN_W = 130
_STRIP_MIN_H = 130

# Cells at least this wide put the condition icon *beside* the hero
# instead of above it — the icon then reads at poster size and the
# temperature still owns the middle of the cell.
_SIDE_BY_SIDE_MIN_W = 170


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

    Every temperature the widget shows — hero included — is a whole
    degree (``22.6`` -> ``23``, ``14.0`` -> ``14``), matching how weather
    apps present temperature and buying several display sizes for the
    hero numerals on a 2" panel. Non-numbers (``"--"``, ``None``) pass
    through untouched.
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


# Widget-scoped CSS. Blitz honours <style> inside the body (including
# media queries), and a cell document only ever contains this widget, so
# these class names cannot collide with anything else on the display.
#
# Sizing notes:
# - .wx-icon is its own clamp rather than .i-lg/.i-md so the icon can be
#   genuinely large next to the hero at 240px but still shrink to a
#   glyph in a 3x3 tile.
# - .wx-col uses flex:1 1 0 (not space-evenly) so every day column is
#   exactly the same width — that is what makes the hi/lo numerals line
#   up vertically across the strip.
_WEATHER_CSS = """
<style>
.wx-main { display: flex; align-items: center; justify-content: center;
           gap: 0.12em; max-width: 100%; }
.wx-main.stack { flex-direction: column; gap: 0.02em; }
.wx-temp { display: flex; align-items: baseline; gap: 0.02em; }
.wx-icon { font-family: "Material Design Icons"; font-weight: 400; line-height: 1;
           font-size: clamp(15px, 33vmin, 78px); }
.wx-main.stack .wx-icon { font-size: clamp(15px, 26vmin, 60px); }
.wx-rule { width: 88%; height: 1px; background: var(--hairline); }
.wx-strip { display: flex; width: 100%; align-items: flex-start; }
.wx-col { display: flex; flex: 1 1 0; min-width: 0; flex-direction: column;
          align-items: center; gap: 0.18em; }
.wx-col .icon { font-size: clamp(11px, 9.5vmin, 21px); }
.wx-hi { font-size: clamp(11px, 8.5vmin, 19px); font-weight: 700; line-height: 1.05;
         color: var(--text-primary); }
.wx-lo { font-size: clamp(10px, 7vmin, 16px); font-weight: 600; line-height: 1.05;
         color: var(--text-tertiary); }
.wx-day { font-size: clamp(9px, 6.5vmin, 13px); font-weight: 700; line-height: 1;
          letter-spacing: 0.1em; color: var(--text-tertiary); }
</style>
"""


def _weather_placeholder() -> str:
    """Placeholder fragment when no weather data is available."""
    icon = mdi_span("weather-cloudy", "icon i-md", "color: var(--text-secondary)")
    return f'<div class="cell">{icon}<div class="t-label hide-short">NO WEATHER DATA</div></div>'


class WeatherWidget(Widget):
    """Widget that displays weather information.

    Fullscreen reads as an Apple-Weather glance:
      caption = condition label (+ humidity when it fits)
      hero    = big condition icon beside whole-degree temperature
      rule    = hairline separator
      strip   = equal-width day columns, each DAY / icon / hi over lo

    Smaller cells shed bands from the bottom up: the strip drops below
    130px, the hero stacks under the icon below 170px wide, and a 3x3
    tile is icon + temperature only.
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

    def _strip_columns(self, ctx: CellContext, forecast: list[dict]) -> list[dict]:
        """Forecast days that fit the cell, or ``[]`` when the strip is off.

        Each column needs roughly 42px to keep ``DAY`` and a two-digit
        temperature legible, so wide cells show every requested day and
        narrower ones truncate rather than crush the columns together.
        """
        if not self.show_forecast:
            return []
        if ctx.width < _STRIP_MIN_W or ctx.height < _STRIP_MIN_H:
            return []
        items = self._visible_forecast(forecast)
        return items[: max(1, int(ctx.width * 0.94 // 42))]

    # ------------------------------------------------------------------
    # Fragment builders
    # ------------------------------------------------------------------

    def _forecast_column(self, day: dict, index: int, high_only: bool) -> str:
        """One day column: ``DAY`` / tinted icon / hi over lo."""
        day_condition = day.get("condition", "sunny")
        day_icon = WEATHER_ICONS.get(day_condition, "weather-sunny")
        day_tint = WEATHER_COLORS.get(day_condition, "var(--warning)")
        day_low = day.get("templow")
        day_name = _parse_forecast_day_name(day.get("datetime", ""), f"D{index + 1}")

        hi = escape(_temp_str(_fmt_num(day.get("temperature", "--"))))
        temps = f'<div class="wx-hi">{hi}</div>'
        if self.show_high_low and not high_only and day_low is not None:
            lo = escape(_temp_str(_fmt_num(day_low)))
            temps += f'<div class="wx-lo">{lo}</div>'

        return (
            '<div class="wx-col">'
            f'<div class="wx-day">{escape(day_name.upper())}</div>'
            f"{mdi_span(day_icon, 'icon', f'color: {day_tint}')}"
            f"{temps}</div>"
        )

    def _forecast_strip(self, ctx: CellContext, items: list[dict]) -> str:
        """Hairline rule + the equal-width day columns."""
        if not items:
            return ""
        # Four or more columns leave under ~50px each; dropping the low
        # keeps the remaining numerals big instead of shrinking them.
        high_only = len(items) > 3
        columns = "".join(self._forecast_column(day, i, high_only) for i, day in enumerate(items))
        return f'<div class="wx-rule"></div><div class="wx-strip">{columns}</div>'

    @staticmethod
    def _caption_html(ctx: CellContext, condition: str, humidity: str | None) -> str:
        """Condition label, with humidity appended when it genuinely fits.

        Humidity is the lower-priority datum, so it is dropped whole
        rather than allowed to push the condition into an ellipsis — a
        caption reading "PARTLY CL… · 62%" trades the useful word for
        the ornamental number.
        """
        avail_w = cell_box(ctx)[0]
        px = label_px(ctx)
        metrics = metrics_for(ctx.theme)
        text = condition.upper()
        if humidity:
            combined = f"{text}   {humidity}"
            if metrics.width(combined, px, "bold", tracking=LABEL_TRACKING) <= avail_w:
                text = combined
        fitted = escape(fit_caption(text, ctx, avail_w))
        return f'<div class="t-label caption-row hide-short">{fitted}</div>'

    def _hero_html(
        self, ctx: CellContext, icon: str, tint: str, temp: Any, avail_w: float, avail_h: float
    ) -> str:
        """Condition icon + whole-degree temperature, side by side or stacked.

        Wide cells set the icon beside the value so both read at poster
        size; narrow ones stack it above, where the value keeps the full
        cell width to itself.
        """
        icon_html = mdi_span(icon, "wx-icon", f"color: {tint}")
        side_by_side = ctx.width >= _SIDE_BY_SIDE_MIN_W
        # The icon's clamp mirrors .wx-icon in the stylesheet below.
        icon_px = max(15.0, min(0.33 * min(ctx.width, ctx.height), 78.0))
        hero_w = avail_w - icon_px * 1.15 if side_by_side else avail_w
        hero_h = avail_h if side_by_side else max(20.0, avail_h - icon_px)

        value = _temp_str(_fmt_num(temp))
        suffix = "°" if value != "--" else ""
        fit = fit_hero(value.rstrip("°"), ctx, max(24.0, hero_w) * _FIT_SLACK, hero_h, suffix=suffix)
        temp_html = f'<div class="t-hero">{hero_block(fit.text, fit.px, suffix=suffix)}</div>'
        stack = "" if side_by_side else " stack"
        return f'<div class="wx-main{stack}">{icon_html}{temp_html}</div>'

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the weather widget."""
        entity = state.entity
        if entity is None:
            return _weather_placeholder()

        condition = entity.state
        icon_name = WEATHER_ICONS.get(condition, "weather-sunny")
        icon_tint = WEATHER_COLORS.get(condition, "var(--warning)")
        humidity = entity.get("humidity", "--")

        columns = self._strip_columns(ctx, state.forecast)
        humidity_text = None
        if self.show_humidity and humidity != "--" and ctx.width >= 180:
            humidity_text = f"{_fmt_num(humidity)}%"

        bands = [
            self._caption_html(ctx, _condition_label(condition), humidity_text),
            self._hero_html(ctx, icon_name, icon_tint, entity.get("temperature", "--")),
        ]

        # Today's hi/lo only earns a chip row when the forecast strip is
        # absent — with the strip up, its first column already says it.
        if not columns and self.show_high_low:
            high, low = self._today_high_low(state.forecast)
            chips = []
            if high is not None:
                chips.append(_tinted_chip(f"{_fmt_num(high)}°", "arrow-up-thin", "var(--warning)"))
            if low is not None:
                chips.append(_tinted_chip(f"{_fmt_num(low)}°", "arrow-down-thin", "var(--info)"))
            if chips:
                bands.append(f'<div class="chips hide-small">{"".join(chips)}</div>')

        bands.append(self._forecast_strip(ctx, columns))
        return f'{_WEATHER_CSS}<div class="cell">{"".join(bands)}</div>'
