"""Chart widget for GeekMagic displays.

Also hosts the small measurement + header primitives shared with the
candlestick widget: both draw an SVG plot under a caption/value header,
and both need to know how tall that plot box will be *before* the
engine lays it out.
"""

from __future__ import annotations

import contextlib
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

from ..htmldoc import css_rgb, svg_sparkline
from .base import Widget, WidgetConfig
from .helpers import truncate_text

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


def fit_px(low: float, value: float, high: float) -> float:
    """Python mirror of CSS ``clamp()`` — keeps layout maths and type in sync."""
    return max(low, min(value, high))


class PlotMetrics(NamedTuple):
    """Measured geometry of a chart cell, in CSS pixels.

    Blitz sizes an inline ``<svg>`` from its viewBox aspect ratio — a
    percentage height against a flex-sized parent does not resolve — so
    the plot box has to be measured in Python and handed to the SVG
    helpers as ``aspect``. Percentage *padding* is equally unusable:
    CSS resolves it against the cell width on both axes, which collapses
    wide/short cells.
    """

    pad_x: int
    pad_y: int
    inner_w: float
    inner_h: float
    label_px: float
    value_px: float
    unit_px: float
    detail_px: float
    gap: float
    compact: bool


def plot_metrics(ctx: CellContext) -> PlotMetrics:
    """Measure a chart cell: insets, type sizes, and the band gap."""
    w, h = ctx.width, ctx.height
    return PlotMetrics(
        pad_x=max(4, round(w * 0.055)),
        pad_y=max(4, round(h * 0.05)),
        inner_w=max(24.0, w - 2.0 * max(4, round(w * 0.055))),
        inner_h=max(24.0, h - 2.0 * max(4, round(h * 0.05))),
        # Mirrors of the kit's clamp() sizing for .t-label / .t-value.
        label_px=fit_px(10.0, min(0.10 * min(w, h), 0.075 * w), 15.0),
        value_px=fit_px(13.0, min(0.17 * min(w, h), 0.115 * w), 31.0),
        unit_px=fit_px(13.0, min(0.17 * min(w, h), 0.115 * w), 31.0) * 0.64,
        detail_px=fit_px(10.0, min(0.115 * min(w, h), 0.085 * w), 17.0),
        gap=max(3.0, h * 0.035),
        compact=h < 100 or w < 100,
    )


class FontRatios(NamedTuple):
    """Average glyph advance widths, in em, for width budgeting."""

    digit: float
    glyph: float
    caption: float  # caps + letterspacing


def font_ratios(ctx: CellContext) -> FontRatios:
    """Advance-width estimates for the theme's font stack.

    Nunito is noticeably narrower than DejaVu, and the DejaVu themes
    also track their caps labels wider (0.18–0.20em vs 0.14em). Budget
    for whichever family the theme actually asks for, so the header row
    never overflows.
    """
    stack = getattr(ctx.theme, "font_stack", "") or ""
    if "Nunito" in stack:
        return FontRatios(digit=0.60, glyph=0.68, caption=0.84)
    return FontRatios(digit=0.66, glyph=0.78, caption=0.94)


def value_header(
    *,
    caption: str,
    value_html: str,
    value_width: float,
    inner_w: float,
    label_px: float,
    ratios: FontRatios,
) -> str:
    """Caption (left) + value (right) sharing one baseline.

    ``value_width`` is the caller's pixel estimate for the value group;
    the caption is truncated in Python to whatever is left, because
    Blitz has no ellipsis and does not clip overflowing text.
    """
    caption_html = ""
    if caption:
        limit = max(3, int((inner_w - value_width - 8.0) / (label_px * ratios.caption)))
        caption_html = f'<span class="t-label">{escape(truncate_text(caption.upper(), limit))}</span>'
    if not caption_html and not value_html:
        return ""
    # Hide classes live on a plain wrapper: an inline display would
    # defeat the kit's display:none media queries.
    return (
        '<div class="hide-short hide-narrow">'
        '<div style="display: flex; align-items: baseline; '
        'justify-content: space-between; gap: 6px">'
        f"{caption_html}{value_html}</div></div>"
    )


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
        """Render the chart: value header, sparkline, low/high range strip."""
        m = plot_metrics(ctx)
        ratios = font_ratios(ctx)

        entity = state.entity
        current_value = None
        unit = ""
        if entity is not None:
            with contextlib.suppress(ValueError, TypeError):
                current_value = float(entity.state)
            unit = entity.unit or ""

        color = css_rgb(self.config.color) if self.config.color else ctx.accent()

        data = state.history
        has_data = state.has_history()
        binary = _is_binary_data(data)

        header = ""
        header_h = 0.0
        footer = ""
        footer_h = 0.0
        if not m.compact:
            header, header_h = self._header(
                self.label_for(entity), m, ratios, current_value, unit, color
            )
            footer, footer_h = self._footer(data, has_data and not binary, m)

        bands = 1 + bool(header) + bool(footer)
        plot_h = max(16.0, m.inner_h - header_h - footer_h - m.gap * (bands - 1))
        # ``aspect`` drives the SVG's rendered height (width / aspect).
        # inner_w deliberately ignores theme chrome padding: the real box
        # can only be narrower, so the plot can only come out shorter
        # than budgeted — never tall enough to overflow the cell.
        aspect = m.inner_w / plot_h

        if has_data:
            stroke_w = fit_px(1.8, 1.6 + min(ctx.width, ctx.height) / 240.0 * 1.6, 3.2)
            spark = svg_sparkline(
                data,
                stroke=color,
                fill_opacity=0.20 if self.fill else 0.0,
                stroke_width=stroke_w,
                aspect=aspect,
                # Bezier smoothing overshoots on square binary traces.
                smooth=not binary,
                show_dot=True,
            )
            plot = f'<div style="width: 100%">{spark}</div>'
        else:
            plot = (
                '<div style="display: flex; align-items: center; justify-content: center; '
                f'height: {plot_h:.0f}px">'
                f'<span style="font-size: {m.value_px * 0.68:.1f}px; font-weight: 700; '
                'letter-spacing: 0.08em; line-height: 1; color: var(--text-tertiary)">'
                "No data</span></div>"
            )

        justify = "center" if bands == 1 else "space-between"
        return (
            f'<div class="cell" style="align-items: stretch; justify-content: {justify}; '
            f'padding: {m.pad_y}px {m.pad_x}px">'
            f"{header}{plot}{footer}"
            "</div>"
        )

    def _header(
        self,
        caption: str,
        m: PlotMetrics,
        ratios: FontRatios,
        current_value: float | None,
        unit: str,
        color: str,
    ) -> tuple[str, float]:
        """Caption + current value; the value carries the chart's tint.

        Value and line read as one visual unit — the gauge-family
        exception to the "hero stays text-primary" rule.
        """
        value_html = ""
        value_w = 0.0
        if self.show_value and current_value is not None:
            value_text = f"{current_value:.1f}"
            value_w = len(value_text) * m.value_px * ratios.digit
            unit_html = ""
            if unit:
                value_w += len(unit) * m.unit_px * ratios.glyph
                unit_html = (
                    f'<span class="t-unit" style="font-size: {m.unit_px:.1f}px; '
                    f'color: {color}">{escape(unit)}</span>'
                )
            value_html = (
                f'<span class="t-value" style="font-size: {m.value_px:.1f}px; color: {color}">'
                f"{escape(value_text)}{unit_html}</span>"
            )

        html = value_header(
            caption=caption,
            value_html=value_html,
            value_width=value_w,
            inner_w=m.inner_w,
            label_px=m.label_px,
            ratios=ratios,
        )
        if not html:
            return "", 0.0
        return html, max(m.value_px if value_html else 0.0, m.label_px if caption else 0.0)

    def _footer(
        self,
        data: list[float],
        enabled: bool,
        m: PlotMetrics,
    ) -> tuple[str, float]:
        """Low / period / high strip — typographic, not arrow soup."""
        if not enabled:
            return "", 0.0
        period = _format_period(self.hours)
        period_html = f'<span class="t-label hide-small">{escape(period)}</span>' if period else ""
        group = "display: flex; align-items: baseline; gap: 0.42em"
        num = (
            f"font-size: {m.detail_px:.1f}px; font-weight: 700; line-height: 1; "
            "letter-spacing: -0.01em; color: var(--text-secondary); white-space: nowrap"
        )
        return (
            '<div class="hide-short hide-narrow">'
            '<div style="display: flex; align-items: baseline; '
            'justify-content: space-between; gap: 6px">'
            f'<span style="{group}"><span class="t-label">L</span>'
            f'<span style="{num}">{escape(f"{min(data):.1f}")}</span></span>'
            f"{period_html}"
            f'<span style="{group}"><span class="t-label">H</span>'
            f'<span style="{num}">{escape(f"{max(data):.1f}")}</span></span>'
            "</div></div>",
            max(m.detail_px, m.label_px),
        )
