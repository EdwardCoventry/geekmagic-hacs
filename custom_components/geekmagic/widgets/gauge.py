"""Gauge widget for GeekMagic displays."""

from __future__ import annotations

import math
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb, mdi_span, svg_arc, svg_ring
from ._gauge import (
    STROKE_UNITS,
    bar_html,
    cell_box,
    fit_caption,
    hero_font_css,
    hero_font_px,
    hero_metrics,
    label_px,
    track_css,
    value_unit_html,
)
from .base import Widget, WidgetConfig
from .helpers import calculate_percent

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

# Bar thickness — ~7% of the cell's short side, floored so a 3x3 cell
# still reads as a bar and capped so a fullscreen cell keeps a slim,
# Activity-style pill rather than a slab.
_BAR_THICKNESS = "clamp(8px, 11vmin, 18px)"
_VBAR_THICKNESS = "clamp(12px, 17vmin, 30px)"

# A round gauge below this diameter cannot hold a caption inside as well
# as the value, so the caption moves above it (or sheds entirely).
_CAPTION_INSIDE_MIN = 132.0
_ROUND_MIN = 44.0
# Past this width/height ratio a centered round gauge strands the cell's
# sides, so the gauge moves left and the text stacks beside it.
_ROW_RATIO = 1.5


class GaugeWidget(Widget):
    """Widget that displays a value as a gauge (bar, ring, or arc)."""

    WIDGET_TYPE: ClassVar[str] = "gauge"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Gauge",
        "needs_entity": True,
        "entity_domains": None,  # Any entity with numeric state
        "options": [
            {
                "key": "style",
                "type": "select",
                "label": "Style",
                "options": ["bar", "ring", "arc"],
                "default": "bar",
            },
            {
                # Only meaningful when style="bar". Auto picks based on
                # cell shape (vertical for tall+narrow cells).
                "key": "orientation",
                "type": "select",
                "label": "Bar Orientation",
                "options": ["auto", "compact", "stacked", "vertical"],
                "default": "auto",
            },
            {"key": "min", "type": "number", "label": "Minimum", "default": 0},
            {"key": "max", "type": "number", "label": "Maximum", "default": 100},
            {"key": "unit", "type": "text", "label": "Unit Override"},
            {"key": "show_name", "type": "boolean", "label": "Show Name", "default": True},
            {"key": "show_value", "type": "boolean", "label": "Show Value", "default": True},
            {"key": "show_unit", "type": "boolean", "label": "Show Unit", "default": True},
            {"key": "icon", "type": "icon", "label": "Icon"},
            {"key": "attribute", "type": "text", "label": "Entity Attribute"},
            {"key": "color_thresholds", "type": "thresholds", "label": "Color Thresholds"},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the gauge widget."""
        super().__init__(config)
        self.style = config.options.get("style", "bar")  # bar, ring, arc
        # auto / compact / stacked / vertical — only meaningful for bar style.
        self.orientation = config.options.get("orientation", "auto")
        self.min_value = config.options.get("min", 0)
        self.max_value = config.options.get("max", 100)
        # Normalise icon: ``ha-icon-picker`` writes ``""`` when cleared.
        self.icon = config.options.get("icon") or None
        self.show_name = config.options.get("show_name", True)
        self.show_value = config.options.get("show_value", True)
        self.show_unit = config.options.get("show_unit", True)
        self.unit = config.options.get("unit", "")
        # Attribute to read value from
        self.attribute = config.options.get("attribute")
        # Color thresholds
        self.color_thresholds = config.options.get("color_thresholds", [])

    def _get_threshold_color(self, value: float) -> tuple[int, int, int] | None:
        """Get color based on value and thresholds."""
        if not self.color_thresholds:
            return None

        sorted_thresholds = sorted(self.color_thresholds, key=lambda t: t.get("value", 0))
        matching_color: tuple[int, int, int] | None = None
        for threshold in sorted_thresholds:
            threshold_value = threshold.get("value", 0)
            threshold_color = threshold.get("color")
            if (
                value >= threshold_value
                and isinstance(threshold_color, list | tuple)
                and len(threshold_color) == 3
            ):
                matching_color = (
                    int(threshold_color[0]),
                    int(threshold_color[1]),
                    int(threshold_color[2]),
                )

        return matching_color

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the gauge widget."""
        entity = state.entity

        value = entity.numeric(self.attribute) if entity is not None else 0.0
        display_value = f"{value:.0f}" if entity is not None else "--"

        # Get unit (override > entity unit, suppressed when show_unit is off).
        if not self.show_unit:
            unit = ""
        else:
            unit = self.unit
            if not unit and entity is not None:
                unit = entity.unit or ""

        percent = calculate_percent(value, self.min_value, self.max_value)
        name = self.label_for(entity) if self.show_name else ""

        if not self.show_value:
            display_value = ""
            unit = ""

        threshold_color = self._get_threshold_color(value)
        rgb = threshold_color or self.config.color
        color = css_rgb(rgb) if rgb else ctx.accent()

        if self.style in ("ring", "arc"):
            return self._render_round(
                ctx,
                name,
                display_value,
                unit,
                percent=percent,
                color=color,
                track=track_css(ctx, rgb, svg=True),
            )
        return self._render_bar(
            ctx,
            name,
            display_value,
            unit,
            percent=percent,
            color=color,
            track=track_css(ctx, rgb),
        )

    # ------------------------------------------------------------------
    # Round gauges (ring / arc)
    # ------------------------------------------------------------------

    def _render_round(
        self,
        ctx: CellContext,
        name: str,
        digits: str,
        unit: str,
        *,
        percent: float,
        color: str,
        track: str,
    ) -> str:
        """Ring or arc: the gauge is sized in Python so it always fits.

        A square gauge in a non-square cell is bounded by the *short*
        side; leaving that to CSS (``aspect-ratio`` on a full-height box)
        overflows tall cells. Knowing the diameter also lets the value be
        sized against the hole rather than the cell, so text never
        collides with the stroke.
        """
        avail_w, avail_h = cell_box(ctx)
        lbl = label_px(ctx)

        if ctx.width > ctx.height * _ROW_RATIO:
            return self._render_round_row(
                ctx, name, digits, unit, percent=percent, color=color, track=track
            )

        # Big gauges hold the caption inside, under the value (Activity
        # style) — that buys the ring the whole cell. Smaller ones put it
        # above; the smallest drop it entirely.
        inside = bool(name) and min(avail_w, avail_h) >= _CAPTION_INSIDE_MIN
        above = bool(name) and not inside and ctx.height >= 92
        reserve = lbl * 1.9 if above else 0.0
        diameter = min(avail_w, avail_h - reserve)
        if diameter < _ROUND_MIN and above:
            # Not enough room for both — the gauge wins.
            above = False
            diameter = min(avail_w, avail_h)
        diameter = max(_ROUND_MIN, diameter)

        label_html = ""
        if digits or unit:
            value_px = self._hole_font_px(diameter, digits, unit)
            if inside:
                value_px *= 0.82
            label_html = self._value_html(digits, unit, value_px, color)
            if inside:
                caption_px = max(9.0, min(lbl, value_px * 0.30))
                hole = diameter - 2 * diameter * STROKE_UNITS / 100
                label_html += (
                    f'<div class="t-label" style="font-size: {caption_px:.1f}px; '
                    f'margin-top: {value_px * 0.16:.1f}px">'
                    f"{escape(fit_caption(ctx, name.upper(), width_px=hole * 0.86))}</div>"
                )

        box = self._gauge_box(diameter, percent, color, track, label_html)
        caption = ""
        if above:
            caption = (
                f'<div class="t-label caption-row">{escape(fit_caption(ctx, name.upper()))}</div>'
            )
        return f'<div class="cell">{caption}{box}</div>'

    def _render_round_row(
        self,
        ctx: CellContext,
        name: str,
        digits: str,
        unit: str,
        *,
        percent: float,
        color: str,
        track: str,
    ) -> str:
        """Wide cell: gauge left, caption + value stacked beside it.

        Centering a circle in a 3:1 cell wastes both sides and shrinks
        the gauge to a token; standing it at the left and setting the
        readout next to it (the Fitness-app row) keeps the gauge at full
        height and the value big.
        """
        avail_w, avail_h = cell_box(ctx)
        gap = avail_w * 0.05
        diameter = max(_ROUND_MIN, min(avail_h, avail_w * 0.46))
        text_w = max(24.0, avail_w - diameter - gap)
        caption = ""
        if name and ctx.height >= 60:
            caption = (
                f'<div class="t-label" style="font-size: {label_px(ctx):.1f}px">'
                f"{escape(fit_caption(ctx, name.upper(), width_px=text_w))}</div>"
            )
        label_html = ""
        if digits or unit:
            hero_px = min(
                hero_font_px(digits, unit, text_w),
                avail_h * (0.52 if caption else 0.74),
            )
            label_html = self._value_html(digits, unit, hero_px, color)
        box = self._gauge_box(diameter, percent, color, track, "")
        return (
            f'<div class="cell row" style="gap: {gap:.0f}px">'
            f"{box}"
            '<div style="flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; '
            'align-items: center; justify-content: center; gap: 6%">'
            f"{caption}{label_html}</div>"
            "</div>"
        )

    @staticmethod
    def _hole_font_px(diameter: float, digits: str, unit: str) -> float:
        """Largest value type that fits inside a round gauge's hole.

        The text's bounding box has to clear the inner circle, so the
        half-diagonal — not the half-width — is what must fit.
        """
        hole = diameter - 2 * diameter * STROKE_UNITS / 100
        chars = hero_metrics(digits, unit)
        fit = 0.47 * hole / math.sqrt((0.325 * chars) ** 2 + 0.16)
        return max(11.0, min(fit * 0.92, hole * 0.62))

    @staticmethod
    def _value_html(digits: str, unit: str, size_px: float, color: str) -> str:
        """Value + unit at an explicit pixel size (gauge-tinted)."""
        return value_unit_html(
            digits,
            unit,
            hero_css=f"{size_px:.1f}px",
            unit_css=f"{size_px * 0.38:.1f}px",
            color=color,
            unit_color=color,
        )

    def _gauge_box(
        self, diameter: float, percent: float, color: str, track: str, label_html: str
    ) -> str:
        """Fixed-size square holding the SVG gauge and its centered label."""
        if self.style == "ring":
            gauge = svg_ring(percent, stroke=color, track=track, stroke_width=STROKE_UNITS)
        else:
            gauge = svg_arc(percent, stroke=color, track=track, stroke_width=STROKE_UNITS)
        overlay = ""
        if label_html:
            # Optical centering: text centered on the geometric middle of
            # a circle reads low, so lift it by a hair.
            overlay = (
                '<div style="position: absolute; inset: 0; display: flex; '
                "flex-direction: column; align-items: center; justify-content: center; "
                f'padding-bottom: {diameter * 0.035:.1f}px">{label_html}</div>'
            )
        return (
            f'<div style="position: relative; flex: none; width: {diameter:.0f}px; '
            f'height: {diameter:.0f}px">{gauge}{overlay}</div>'
        )

    # ------------------------------------------------------------------
    # Bar gauges
    # ------------------------------------------------------------------

    def _render_bar(
        self,
        ctx: CellContext,
        name: str,
        digits: str,
        unit: str,
        *,
        percent: float,
        color: str,
        track: str,
    ) -> str:
        """Bar gauge — horizontal by default, vertical for tall narrow cells."""
        vertical = self.orientation == "vertical" or (
            self.orientation == "auto" and ctx.height > ctx.width * 1.6
        )
        icon_html = mdi_span(self.icon, "icon i-sm", f"color: {color}") if self.icon else ""

        if not vertical:
            caption = self._caption(ctx, name, icon_html)
            bar = bar_html(percent, color=color, track=track, thickness=_BAR_THICKNESS)
            return f'<div class="cell">{caption}{self._hero(digits, unit, color)}{bar}</div>'

        vbar = bar_html(percent, color=color, track=track, thickness=_VBAR_THICKNESS, vertical=True)
        if ctx.width > ctx.height * 1.15:
            # Wide cell, vertical bar: stand the bar up the left edge and
            # set the label + value beside it instead of stranding a stub
            # of a bar in the middle.
            caption = self._caption(ctx, name, icon_html, width_ratio=0.6)
            hero = self._hero(digits, unit, color, cap_vw=24.0, cap_vmin=44.0)
            return (
                '<div class="cell row" style="gap: 6%">'
                f'<div style="align-self: stretch; display: flex; flex: none">{vbar}</div>'
                '<div style="flex: 1 1 0; min-width: 0; display: flex; '
                "flex-direction: column; align-items: center; justify-content: center; "
                f'gap: 4%">{caption}{hero}</div>'
                "</div>"
            )

        # Tall cell: caption above, bar taking every spare pixel, value
        # under it. The value stays deliberately smaller than a
        # horizontal bar's hero so the column of colour stays the subject.
        caption = self._caption(ctx, name, icon_html)
        hero = self._hero(digits, unit, color, cap_vw=27.0, cap_vmin=30.0)
        return (
            '<div class="cell">'
            f"{caption}"
            '<div style="flex: 1 1 auto; min-height: 0; width: 100%; display: flex; '
            f'justify-content: center">{vbar}</div>'
            f"{hero}"
            "</div>"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hero(
        digits: str,
        unit: str,
        color: str,
        *,
        cap_vw: float = 38.0,
        cap_vmin: float = 48.0,
    ) -> str:
        """Fluid hero value. Gauge-family exception: it wears the fill's
        tint so value and bar read as one object (Apple Activity)."""
        hero_css, unit_css = hero_font_css(digits, unit, cap_vw=cap_vw, cap_vmin=cap_vmin)
        return value_unit_html(
            digits, unit, hero_css=hero_css, unit_css=unit_css, color=color, unit_color=color
        )

    @staticmethod
    def _caption(
        ctx: CellContext,
        name: str,
        icon_html: str = "",
        *,
        width_ratio: float = 1.0,
    ) -> str:
        """Caps caption band, Python-truncated to the cell width."""
        if not name:
            return ""
        text = fit_caption(
            ctx,
            name.upper(),
            reserve_em=1.6 if icon_html else 0.0,
            width_px=ctx.width * 0.90 * width_ratio,
        )
        return f'<div class="t-label caption-row hide-short">{icon_html}{escape(text)}</div>'
