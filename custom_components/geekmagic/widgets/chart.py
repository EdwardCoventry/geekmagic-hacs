"""Chart widget for GeekMagic displays."""

from __future__ import annotations

import contextlib
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb, mdi_span, svg_sparkline
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


def _format_period(hours: float) -> str:
    """Format a chart period as a compact label (e.g. "24h", "15m")."""
    if hours <= 0:
        return ""
    if hours < 1:
        return f"{round(hours * 60)}m"
    return f"{round(hours)}h"


def _is_binary_data(data: list[float]) -> bool:
    """Check if data is binary (all 0.0 or 1.0)."""
    if not data:
        return False
    return all(v in {0.0, 1.0} for v in data)


class ChartWidget(Widget):
    """Widget that displays a sparkline chart from entity history."""

    WIDGET_TYPE: ClassVar[str] = "chart"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Chart",
        "needs_entity": True,
        "entity_domains": None,  # Any entity with numeric state
        "options": [
            {
                "key": "period",
                "type": "select",
                "label": "Period",
                "options": ["5 min", "15 min", "1 hour", "6 hours", "24 hours"],
                "default": "24 hours",
            },
            {
                "key": "show_value",
                "type": "boolean",
                "label": "Show Current Value",
                "default": True,
            },
            {
                "key": "show_range",
                "type": "boolean",
                "label": "Show Min/Max Range",
                "default": True,
            },
            {"key": "fill", "type": "boolean", "label": "Fill Area", "default": True},
            {
                "key": "color_gradient",
                "type": "boolean",
                "label": "Value Gradient",
                "default": False,
            },
        ],
    }

    PERIOD_TO_HOURS: ClassVar[dict[str, float]] = {
        "5 min": 5 / 60,
        "15 min": 15 / 60,
        "1 hour": 1,
        "6 hours": 6,
        "24 hours": 24,
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the chart widget."""
        super().__init__(config)
        period = config.options.get("period")
        if period and isinstance(period, str):
            self.hours = self.PERIOD_TO_HOURS.get(period, 24)
        elif period and isinstance(period, int | float):
            self.hours = period / 60
        else:
            self.hours = config.options.get("hours", 24)
        self.show_value = config.options.get("show_value", True)
        self.show_range = config.options.get("show_range", True)
        self.fill = config.options.get("fill", True)  # Default to filled area
        self.color_gradient = config.options.get("color_gradient", False)

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the chart widget: caption row above a fluid sparkline."""
        entity = state.entity
        current_value = None
        unit = ""

        if entity is not None:
            with contextlib.suppress(ValueError, TypeError):
                current_value = float(entity.state)
            unit = entity.unit or ""
        label = self.label_for(entity)

        color = css_rgb(self.config.color) if self.config.color else ctx.accent()

        # Caption row: name left, current value right (value shares the
        # chart tint — gauge-family style, value + line read as one unit).
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
                f'line-height: 1; white-space: nowrap; color: {color}">'
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

        # Sparkline fills the remaining space.
        if state.has_history():
            spark = svg_sparkline(
                state.history,
                stroke=color,
                fill_opacity=0.15 if self.fill else 0.0,
            )
            chart = f'<div style="flex: 1; min-height: 0">{spark}</div>'
        else:
            chart = (
                '<div style="flex: 1; min-height: 0; display: flex; align-items: center; '
                "justify-content: center; color: var(--text-secondary); "
                'font-size: clamp(11px, 13vmin, 20px); font-weight: 600">No data</div>'
            )

        # Range footer: low (arrow-down) left, period center, high
        # (arrow-up) right. Suppressed for binary data and short cells.
        footer = ""
        data = state.history
        if self.show_range and state.has_history() and not _is_binary_data(data):
            min_text = f"{min(data):.1f}"
            max_text = f"{max(data):.1f}"
            period = _format_period(self.hours)
            period_html = (
                '<span class="hide-small" style="color: var(--text-tertiary)">'
                f"{escape(period)}</span>"
                if period
                else ""
            )
            footer = (
                '<div class="hide-short">'
                '<div style="display: flex; align-items: center; '
                "justify-content: space-between; gap: 4px; color: var(--text-secondary); "
                'font-size: clamp(10px, 11vmin, 18px); font-weight: 600; line-height: 1">'
                '<span style="display: flex; align-items: center; gap: 2px">'
                f"{mdi_span('arrow-down', 'icon')}{escape(min_text)}</span>"
                f"{period_html}"
                '<span style="display: flex; align-items: center; gap: 2px">'
                f"{mdi_span('arrow-up', 'icon')}{escape(max_text)}</span>"
                "</div></div>"
            )

        return (
            '<div class="cell" style="align-items: stretch; gap: 4px; padding: 5% 7%">'
            f"{header}{chart}{footer}"
            "</div>"
        )
