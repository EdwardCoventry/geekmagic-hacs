"""Progress widget for GeekMagic displays."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb, css_rgba, mdi_span
from ._card import card_html, chip_html
from .base import Widget, WidgetConfig
from .helpers import format_number, truncate_text

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

# Legacy thin/normal/thick bar styles expressed as fluid CSS heights.
# (Old Pillow ratios were 0.10 / 0.17 / 0.25 of cell height.)
_BAR_HEIGHT_CSS: dict[str, str] = {
    "thin": "clamp(5px, 8vmin, 13px)",
    "normal": "clamp(8px, 13vmin, 20px)",
    "thick": "clamp(11px, 19vmin, 30px)",
}


def _track_color(ctx: CellContext, rgb: tuple[int, int, int] | None) -> str:
    """Tinted gauge track, Apple Activity style (theme-controlled)."""
    if rgb is None and ctx.theme is not None:
        rgb = ctx.theme.get_accent_color(ctx.slot_index)
    if rgb is not None and ctx.theme is not None and ctx.theme.tint_track:
        return css_rgba(rgb, ctx.theme.tint_track_opacity)
    return "rgba(128, 128, 128, 0.20)"


def _bar_html(percent: float, color: str, track: str, height_css: str) -> str:
    """Horizontal progress track + fill (same pattern as gauge bars)."""
    return (
        f'<div style="width: 100%; height: {height_css}; background: {track}; '
        'border-radius: 999px; overflow: hidden">'
        f'<div style="width: {percent:.1f}%; height: 100%; background: {color}; '
        'border-radius: 999px"></div>'
        "</div>"
    )


class ProgressWidget(Widget):
    """Widget that displays progress with label."""

    WIDGET_TYPE: ClassVar[str] = "progress"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Progress",
        "needs_entity": True,
        "entity_domains": None,  # Any entity with numeric state
        "options": [
            {"key": "target", "type": "number", "label": "Target Value", "default": 100},
            {"key": "unit", "type": "text", "label": "Unit"},
            {"key": "show_target", "type": "boolean", "label": "Show Target", "default": True},
            {"key": "icon", "type": "icon", "label": "Icon"},
            {
                "key": "bar_height",
                "type": "select",
                "label": "Bar Height",
                "options": ["thin", "normal", "thick"],
                "default": "normal",
            },
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the progress widget."""
        super().__init__(config)
        self.target = config.options.get("target", 100)
        self.unit = config.options.get("unit", "")
        self.show_target = config.options.get("show_target", True)
        self.icon = config.options.get("icon")
        self.bar_height_style = config.options.get("bar_height", "normal")

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the progress widget: caption / percent hero / chip / bar."""
        entity = state.entity
        value = entity.numeric() if entity is not None else 0.0

        unit = self.unit
        if not unit and entity:
            unit = entity.unit or ""

        label = self.label_for(entity, fallback="Progress")

        target = self.target or 100
        percent = min(100, (value / target) * 100) if target > 0 else 0

        # Supporting chip: "{value}/{target} {unit}" — ``format_number``
        # abbreviates large values (e.g. 1.5k).
        value_str = format_number(value)
        if self.show_target:
            value_str = f"{value_str}/{format_number(target)}"
        if unit:
            value_str = f"{value_str} {unit}"

        rgb = self.config.color
        color = css_rgb(rgb) if rgb else ctx.accent()
        track = _track_color(ctx, rgb)
        bar_height = _BAR_HEIGHT_CSS.get(self.bar_height_style, _BAR_HEIGHT_CSS["normal"])

        bar = f'<div style="width: 88%">{_bar_html(percent, color, track, bar_height)}</div>'

        return card_html(
            caption=label,
            icon=self.icon,
            icon_color=color,
            icon_role="feature",
            hero=f"{percent:.0f}%",
            chips=[chip_html(value_str)] if value_str else None,
            extra=bar,
        )


class MultiProgressWidget(Widget):
    """Widget that displays multiple progress items."""

    WIDGET_TYPE: ClassVar[str] = "multi_progress"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Multi Progress",
        "needs_entity": False,
        "options": [
            {"key": "title", "type": "text", "label": "Title"},
            {"key": "items", "type": "progress_items", "label": "Progress Items"},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the multi-progress widget."""
        super().__init__(config)
        self.items = config.options.get("items", [])
        self.title = config.options.get("title")

    def get_entities(self) -> list[str]:
        """Return list of entity IDs."""
        return [item.get("entity_id") for item in self.items if item.get("entity_id")]

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render labeled progress bars stacked in a flex column."""
        rows: list[str] = []

        # Blitz has no text truncation, so size fonts in Python and
        # truncate labels to the space the value line leaves them.
        vmin = min(ctx.width, ctx.height)
        text_px = max(10.0, min(17.0, 0.11 * vmin))
        label_px = max(9.0, min(17.0, 0.11 * vmin, 0.08 * ctx.width))
        label_cw = label_px * 0.70  # caps + letter-spacing
        avail = ctx.width * 0.90  # cell padding is 5% each side
        # The raw value column is hidden by .hide-small below 130px.
        value_shown = ctx.width >= 130 and ctx.height >= 130

        if self.title:
            title_text = truncate_text(self.title.upper(), max(4, int(avail // label_cw)))
            rows.append(
                '<div class="t-label hide-short" style="text-align: left">'
                f"{escape(title_text)}</div>"
            )

        # Row text scales with the cell but stays list-sized (several
        # rows must share the cell, unlike a single hero value).
        text_css = (
            f"font-size: {text_px:.1f}px; font-weight: 700; line-height: 1; white-space: nowrap;"
        )
        # Like .t-label but with a smaller floor so three items still
        # fit a 3x3 cell.
        label_css = (
            f"font-size: {label_px:.1f}px; font-weight: 600; "
            "line-height: 1; letter-spacing: 0.05em; color: var(--text-tertiary); "
            "white-space: nowrap; text-align: left;"
        )

        for i, item in enumerate(self.items):
            entity_id = item.get("entity_id")
            entity = state.get_entity(entity_id) if entity_id else None
            value = entity.numeric() if entity is not None else 0.0

            label = item.get("label", "")
            if entity and not label:
                label = entity.friendly_name
            label = label or entity_id or "Item"

            unit = item.get("unit", "")
            if entity and not unit:
                unit = entity.unit or ""

            target = item.get("target", 100)
            percent = min(100, (value / target) * 100) if target > 0 else 0

            rgb = item.get("color")
            if isinstance(rgb, list):
                rgb = tuple(rgb)
            if rgb is None and ctx.theme is not None:
                rgb = ctx.theme.get_accent_color(i)
            color = css_rgb(rgb) if rgb else "var(--primary)"
            track = _track_color(ctx, rgb)

            value_text = f"{value:.0f}/{target:.0f}"
            if unit:
                value_text += f" {unit}"

            icon = item.get("icon")
            icon_html = mdi_span(icon, "icon i-sm", f"color: {color}") if icon else ""

            # Truncate the label to whatever the icon + value leave it.
            label_budget = avail - 8
            if icon_html:
                label_budget -= text_px * 1.3
            if value_shown:
                label_budget -= len(value_text) * text_px * 0.52
            label_text = truncate_text(label.upper(), max(3, int(label_budget // label_cw) + 1))

            # Label line: icon + caps label left, raw value right (the
            # raw value sheds first in small cells; percent survives).
            label_row = (
                '<div style="display: flex; align-items: center; gap: 4px">'
                f"{icon_html}"
                f'<span style="{label_css} flex: 1 1 0; min-width: 0">'
                f"{escape(label_text)}</span>"
                f'<span class="hide-small" style="{text_css}">{escape(value_text)}</span>'
                "</div>"
            )
            # Bar line: slim track + percent readout.
            bar_row = (
                '<div style="display: flex; align-items: center; gap: 6px">'
                '<div style="flex: 1; min-width: 0">'
                f"{_bar_html(percent, color, track, 'clamp(4px, 6vmin, 15px)')}"
                "</div>"
                f'<span style="{text_css}">{percent:.0f}%</span>'
                "</div>"
            )
            rows.append(
                '<div style="display: flex; flex-direction: column; '
                'gap: clamp(1px, 1.5vmin, 4px)">'
                f"{label_row}{bar_row}</div>"
            )

        return (
            '<div class="cell" style="align-items: stretch; padding: 3% 5%; '
            'gap: clamp(2px, 3vmin, 10px)">'
            f"{''.join(rows)}</div>"
        )
