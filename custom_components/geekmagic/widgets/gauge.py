"""Gauge widget for GeekMagic displays."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb, css_rgba, mdi_span, svg_arc, svg_ring
from .base import Widget, WidgetConfig
from .helpers import calculate_percent, format_value_with_unit

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


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

        threshold_color = self._get_threshold_color(value)
        rgb = threshold_color or self.config.color
        color = css_rgb(rgb) if rgb else ctx.accent()
        # Tinted track, Apple Activity style (theme-controlled opacity).
        track_rgb = threshold_color or self.config.color
        if track_rgb is None and ctx.theme is not None:
            track_rgb = ctx.theme.get_accent_color(ctx.slot_index)
        track = (
            css_rgba(track_rgb, ctx.theme.tint_track_opacity)
            if (track_rgb is not None and ctx.theme is not None and ctx.theme.tint_track)
            else "rgba(128, 128, 128, 0.20)"
        )

        value_text = format_value_with_unit(display_value, unit) if self.show_value else ""

        if self.style in ("ring", "arc"):
            return self._render_round(name, value_text, percent, color, track)
        return self._render_bar(ctx, name, value_text, percent=percent, color=color, track=track)

    def _render_round(
        self, name: str, value_text: str, percent: float, color: str, track: str
    ) -> str:
        """Ring or arc gauge: SVG fills the cell, value centered inside."""
        label_html = ""
        if value_text:
            # Gauge-family exception: value shares the gauge tint so
            # value + fill read as one visual unit.
            label_html = f'<div class="t-value" style="color: {color}">{escape(value_text)}</div>'
        if self.style == "ring":
            gauge = svg_ring(percent, stroke=color, track=track, label_html=label_html)
        else:
            arc = svg_arc(percent, stroke=color, track=track)
            gauge = (
                '<div style="position:relative;height:100%;aspect-ratio:1;margin:0 auto">'
                f"{arc}"
                '<div style="position:absolute;inset:0;display:flex;align-items:center;'
                f'justify-content:center">{label_html}</div></div>'
            )
        caption = (
            f'<div class="t-label caption-row hide-short">{escape(name.upper())}</div>'
            if name
            else ""
        )
        return (
            '<div class="cell" style="gap: 4px; padding: 4%">'
            f"{caption}"
            f'<div style="flex: 1; min-height: 0; width: 100%">{gauge}</div>'
            "</div>"
        )

    def _render_bar(
        self,
        ctx: CellContext,
        name: str,
        value_text: str,
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

        if vertical:
            bar = (
                f'<div style="flex:1; min-height:0; width: clamp(14px, 22vw, 34px); '
                f"background: {track}; border-radius: 999px; position: relative; "
                'margin: 0 auto">'
                '<div style="position:absolute; bottom:0; left:0; right:0; '
                f'height: {percent:.1f}%; background: {color}; border-radius: 999px"></div>'
                "</div>"
            )
            caption_inner = f"{icon_html}{escape(name.upper())}"
            label = (
                f'<div class="t-label caption-row hide-short">{caption_inner}</div>' if name else ""
            )
            value = f'<div class="t-value">{escape(value_text)}</div>' if value_text else ""
            return f'<div class="cell" style="gap:5px; padding:5%">{label}{bar}{value}</div>'

        # Horizontal: stacked caption / hero value / track. The hero
        # shares the bar tint (gauge-family exception) and the caption
        # sheds in short cells, leaving value + bar.
        bar = (
            f'<div style="width:100%; height: clamp(9px, 13vmin, 20px); '
            f'background: {track}; border-radius: 999px; overflow: hidden">'
            f'<div style="width: {percent:.1f}%; height: 100%; background: {color}; '
            'border-radius: 999px"></div>'
            "</div>"
        )
        caption = (
            f'<div class="t-label caption-row hide-short">{icon_html}{escape(name.upper())}</div>'
            if name
            else ""
        )
        value = (
            f'<div class="t-hero" style="color: {color}">{escape(value_text)}</div>'
            if value_text
            else ""
        )
        return (
            '<div class="cell" style="align-items: stretch; padding: 6%; gap: 5px">'
            f"{caption}{value}{bar}"
            "</div>"
        )
