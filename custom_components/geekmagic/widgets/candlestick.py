"""Candlestick chart widget for GeekMagic displays."""

from __future__ import annotations

import contextlib
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


def aggregate_ohlc(
    timestamped_values: list[tuple[float, float]],
    interval_seconds: int,
    candle_count: int,
) -> list[tuple[float, float, float, float]]:
    """Aggregate timestamped values into OHLC candles.

    Args:
        timestamped_values: List of (timestamp, value) tuples, sorted by time.
        interval_seconds: Duration of each candle in seconds.
        candle_count: Number of candles to produce.

    Returns:
        List of (open, high, low, close) tuples, one per candle.
    """
    if not timestamped_values:
        return []

    # Determine the end time from the last data point
    end_ts = timestamped_values[-1][0]
    start_ts = end_ts - (candle_count * interval_seconds)

    # Bucket values into candles
    buckets: list[list[float]] = [[] for _ in range(candle_count)]

    for ts, value in timestamped_values:
        if ts < start_ts:
            continue
        bucket_idx = int((ts - start_ts) / interval_seconds)
        # Clamp to last bucket for points exactly at the end boundary
        bucket_idx = min(bucket_idx, candle_count - 1)
        if bucket_idx >= 0:
            buckets[bucket_idx].append(value)

    # Convert buckets to OHLC tuples
    candles: list[tuple[float, float, float, float]] = []
    last_close: float | None = None

    # Find first non-empty bucket to seed last_close
    for values in buckets:
        if values:
            last_close = values[0]
            break

    if last_close is None:
        return []

    # Also check for values before start_ts to seed last_close
    for ts, value in timestamped_values:
        if ts < start_ts:
            last_close = value
        else:
            break

    for values in buckets:
        if values:
            o = values[0]
            h = max(values)
            low = min(values)
            c = values[-1]
            candles.append((o, h, low, c))
            last_close = c
        else:
            # Empty bucket: flat candle at last close
            candles.append((last_close, last_close, last_close, last_close))

    return candles


def extract_timestamped_values(history_states: list) -> list[tuple[float, float]]:
    """Extract (timestamp, value) pairs from recorder history states.

    Args:
        history_states: List of State objects from the recorder.

    Returns:
        List of (timestamp_seconds, numeric_value) tuples.
    """
    timestamped: list[tuple[float, float]] = []
    for state_obj in history_states:
        try:
            state_value = state_obj.state if hasattr(state_obj, "state") else state_obj.get("state")
            ts = (
                state_obj.last_changed.timestamp()
                if hasattr(state_obj, "last_changed")
                else state_obj.get("last_changed", 0)
            )
            if state_value is not None:
                timestamped.append((float(ts), float(state_value)))
        except (ValueError, TypeError, AttributeError):
            continue
    return timestamped


INTERVAL_TO_SECONDS: dict[str, int] = {
    "1 hour": 3600,
    "4 hours": 14400,
    "1 day": 86400,
}


def _candles_svg(
    data: list[tuple[float, float, float, float]],
    up_color: str,
    down_color: str,
) -> str:
    """Build an OHLC candle chart as inline SVG.

    Uses a 100x100 viewBox with non-uniform scaling so it stretches to
    whatever box the layout gives it. Wicks keep a constant on-screen
    width via ``vector-effect: non-scaling-stroke``. Colors must be
    concrete CSS colors — ``var()`` does not resolve inside SVG paint
    attributes in the Blitz engine.
    """
    # Find global min/max for scaling
    all_highs = [c[1] for c in data]
    all_lows = [c[2] for c in data]
    data_min = min(all_lows)
    data_max = max(all_highs)

    data_range = data_max - data_min
    if data_range == 0:
        data_range = 1.0
        data_min -= 0.5
        data_max += 0.5

    # Small margin so candles never touch the edges
    margin = data_range * 0.05
    data_min -= margin
    data_max += margin
    data_range = data_max - data_min

    num_candles = len(data)
    # Each candle gets equal width with a gap between them
    candle_total = 100.0 / num_candles
    gap = candle_total * 0.2
    body_w = max(candle_total - gap, 0.5)

    def val_to_y(val: float) -> float:
        return 100.0 - (val - data_min) / data_range * 100.0

    parts = [
        '<svg viewBox="0 0 100 100" preserveAspectRatio="none" '
        'style="width:100%;height:100%;display:block">'
    ]
    for i, (o, h, low, c) in enumerate(data):
        bullish = c >= o
        color = up_color if bullish else down_color

        body_x = i * candle_total + gap / 2
        center_x = body_x + body_w / 2

        wick_top = val_to_y(h)
        wick_bottom = val_to_y(low)
        body_top = val_to_y(max(o, c))
        body_bottom = val_to_y(min(o, c))

        # Ensure the body stays visible (flat/doji candles)
        if body_bottom - body_top < 1.0:
            body_top = min(body_top, 99.0)
            body_bottom = body_top + 1.0

        parts.append(
            f'<line x1="{center_x:.2f}" x2="{center_x:.2f}" '
            f'y1="{wick_top:.2f}" y2="{wick_bottom:.2f}" '
            f'stroke="{color}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>'
        )
        parts.append(
            f'<rect x="{body_x:.2f}" y="{body_top:.2f}" '
            f'width="{body_w:.2f}" height="{body_bottom - body_top:.2f}" fill="{color}"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


class CandlestickWidget(Widget):
    """Widget that displays a candlestick chart from entity history."""

    WIDGET_TYPE: ClassVar[str] = "candlestick"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Candlestick Chart",
        "needs_entity": True,
        "entity_domains": None,
        "options": [
            {
                "key": "candle_interval",
                "type": "select",
                "label": "Candle Interval",
                "options": ["1 hour", "4 hours", "1 day"],
                "default": "4 hours",
            },
            {
                "key": "candle_count",
                "type": "number",
                "label": "Number of Candles",
                "min": 5,
                "max": 40,
                "default": 20,
            },
            {
                "key": "show_value",
                "type": "boolean",
                "label": "Show Current Value",
                "default": True,
            },
        ],
    }

    INTERVAL_TO_HOURS: ClassVar[dict[str, float]] = {
        "1 hour": 1,
        "4 hours": 4,
        "1 day": 24,
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the candlestick widget."""
        super().__init__(config)
        self.candle_interval: str = config.options.get("candle_interval", "4 hours")
        self.candle_count: int = int(config.options.get("candle_count", 20))
        self.show_value: bool = config.options.get("show_value", True)

    @property
    def hours(self) -> float:
        """Total hours of history needed."""
        interval_hours = self.INTERVAL_TO_HOURS.get(self.candle_interval, 4)
        return interval_hours * self.candle_count

    @property
    def interval_seconds(self) -> int:
        """Candle interval in seconds."""
        return INTERVAL_TO_SECONDS.get(self.candle_interval, 14400)

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the candlestick chart: caption row above stretched candles."""
        entity = state.entity
        current_value = None
        unit = ""

        if entity is not None:
            with contextlib.suppress(ValueError, TypeError):
                current_value = float(entity.state)
            unit = entity.unit or ""
        label = self.label_for(entity)

        data = list(state.candlestick_data)

        # Bull/bear tints resolved from the theme: var() does not resolve
        # inside SVG paint attributes, so the SVG needs concrete colors.
        # (HTML text can still use the CSS variables.)
        up_color = css_rgb(ctx.theme.success) if ctx.theme else "var(--success)"
        down_color = css_rgb(ctx.theme.error) if ctx.theme else "var(--error)"

        # Value color reflects the most recent candle direction.
        value_color = "var(--text-secondary)"
        if data:
            last = data[-1]
            value_color = "var(--success)" if last[3] >= last[0] else "var(--error)"

        # Caption row: name left, current value right.
        header_parts: list[str] = []
        if label:
            header_parts.append(
                '<span class="t-label" style="overflow: hidden; '
                'text-overflow: ellipsis; white-space: nowrap">'
                f"{escape(label.upper())}</span>"
            )
        if self.show_value and current_value is not None:
            value_str = f"{current_value:.1f}{unit}"
            header_parts.append(
                f'<span style="font-size: clamp(11px, 13vmin, 22px); font-weight: 700; '
                f'line-height: 1; white-space: nowrap; color: {value_color}">'
                f"{escape(value_str)}</span>"
            )
        # Note: the flex row lives inside a plain hide-short wrapper — an
        # inline display style would defeat the kit's display:none media query.
        header = ""
        if header_parts:
            header = (
                '<div class="hide-short">'
                '<div style="display: flex; align-items: center; '
                'justify-content: space-between; gap: 6px">'
                f"{''.join(header_parts)}</div></div>"
            )

        # Candle chart fills the remaining space.
        if data:
            svg = _candles_svg(data, up_color, down_color)
            chart = f'<div style="flex: 1; min-height: 0">{svg}</div>'
        else:
            chart = (
                '<div style="flex: 1; min-height: 0; display: flex; align-items: center; '
                "justify-content: center; color: var(--text-secondary); "
                'font-size: clamp(11px, 13vmin, 20px); font-weight: 600">No data</div>'
            )

        return (
            '<div class="cell" style="align-items: stretch; gap: 4px; padding: 5% 7%">'
            f"{header}{chart}"
            "</div>"
        )
