"""Progress widget for GeekMagic displays."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb, mdi_span
from ._card import chip_html
from ._gauge import (
    bar_html,
    cell_box,
    char_em,
    fit_caption,
    hero_font_css,
    label_px,
    track_css,
    value_unit_html,
)
from .base import Widget, WidgetConfig
from .helpers import format_number, truncate_text

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

# Progress bars are supporting evidence for the percent hero, not the
# subject (that's what the gauge widget is for), so they run slimmer
# than a bar gauge. Legacy thin/normal/thick option, re-tuned.
_BAR_HEIGHT_CSS: dict[str, str] = {
    "thin": "clamp(4px, 5vmin, 9px)",
    "normal": "clamp(6px, 8vmin, 14px)",
    "thick": "clamp(9px, 13vmin, 22px)",
}

# Below this the multi-progress rows would be thinner than their own
# type; extra items are dropped rather than crushed.
_MIN_ROW_PX = 13.0


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
        self.icon = config.options.get("icon") or None
        self.bar_height_style = config.options.get("bar_height", "normal")

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the widget: caption / percent hero / bar / value chip."""
        entity = state.entity
        value = entity.numeric() if entity is not None else 0.0

        unit = self.unit
        if not unit and entity:
            unit = entity.unit or ""

        label = self.label_for(entity, fallback="Progress")

        target = self.target or 100
        percent = min(100, (value / target) * 100) if target > 0 else 0

        rgb = self.config.color
        color = css_rgb(rgb) if rgb else ctx.accent()
        bar_height = _BAR_HEIGHT_CSS.get(self.bar_height_style, _BAR_HEIGHT_CSS["normal"])

        icon_html = mdi_span(self.icon, "icon i-sm", f"color: {color}") if self.icon else ""
        caption = (
            '<div class="t-label caption-row hide-short">'
            f"{icon_html}"
            f"{escape(fit_caption(ctx, label.upper(), reserve_em=1.6 if icon_html else 0.0))}"
            "</div>"
        )
        # The percent is the hero and stays theme text — the tint lives
        # in the icon and the bar fill (one accent per cell).
        hero_css, unit_css = hero_font_css(f"{percent:.0f}", "%")
        hero = value_unit_html(f"{percent:.0f}", "%", hero_css=hero_css, unit_css=unit_css)
        bar = bar_html(percent, color=color, track=track_css(ctx, rgb), thickness=bar_height)
        chip = self._value_chip(ctx, value, target, unit)
        return f'<div class="cell">{caption}{hero}{bar}{chip}</div>'

    def _value_chip(self, ctx: CellContext, value: float, target: float, unit: str) -> str:
        """Raw progress as a pill: "4.2k of 10k steps".

        Degrades by dropping the least important part first (unit, then
        target) so the chip never spills out of a narrow cell.
        """
        amount = format_number(value)
        variants = [amount]
        if self.show_target:
            variants.insert(0, f"{amount} of {format_number(target)}")
        if unit:
            variants.insert(0, f"{variants[0]} {unit}")

        px = max(10.0, min(0.11 * min(ctx.width, ctx.height), 16.0))
        avail_w, _ = cell_box(ctx)
        budget = (avail_w - 1.9 * px) / (px * char_em(ctx))
        text = next((v for v in variants if len(v) <= budget), "")
        if not text:
            text = truncate_text(variants[-1], max(3, int(budget)))
        return f'<div class="chips hide-small">{chip_html(text)}</div>'


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
        """Render progress rows that share the cell height evenly.

        Every row is ``flex: 1`` so the rhythm is even by construction —
        no dead space at the bottom, no rows crushed together at the top.
        """
        avail_w, avail_h = cell_box(ctx)
        lbl_px = label_px(ctx)

        # The title is the first thing to go: rows carry the meaning.
        title_html = ""
        if self.title and min(ctx.width, ctx.height) >= 130:
            title_html = (
                '<div class="t-label" style="flex: none; text-align: left">'
                f"{escape(fit_caption(ctx, self.title.upper()))}</div>"
            )
            avail_h -= lbl_px * 1.8

        rows_fit = max(1, int(avail_h / _MIN_ROW_PX))
        items = self.items[:rows_fit]
        if not items:
            return f'<div class="cell" style="align-items: stretch">{title_html}</div>'

        row_h = avail_h / len(items)
        # Row type is list-sized, not hero-sized: several rows share the
        # cell, so it scales with the row rather than the cell.
        text_px = max(9.0, min(17.0, 0.11 * min(ctx.width, ctx.height), row_h * 0.44))
        label_px_row = max(8.0, min(text_px * 0.86, 0.075 * ctx.width))
        bar_px = max(4.0, min(11.0, row_h * 0.22))
        # One column for every percent so the bars all end on the same
        # pixel — a ragged right edge is what makes stacked bars look
        # accidental.
        pct_w = 4.2 * text_px * char_em(ctx)
        # The raw value column only survives in cells the kit keeps it in.
        value_shown = ctx.width >= 130 and ctx.height >= 130
        labels_shown = ctx.height >= 100

        text_css = f"font-size: {text_px:.1f}px; font-weight: 700; line-height: 1;"
        label_css = (
            f"font-size: {label_px_row:.1f}px; font-weight: 700; line-height: 1; "
            "letter-spacing: 0.1em; color: var(--text-tertiary); text-align: left;"
        )

        rows = [
            self._row_html(
                ctx,
                state,
                item,
                index,
                avail_w=avail_w,
                text_px=text_px,
                label_px_row=label_px_row,
                bar_px=bar_px,
                pct_w=pct_w,
                text_css=text_css,
                label_css=label_css,
                value_shown=value_shown,
                labels_shown=labels_shown,
            )
            for index, item in enumerate(items)
        ]
        return (
            '<div class="cell" style="align-items: stretch; gap: 2%">'
            f"{title_html}{''.join(rows)}</div>"
        )

    def _row_html(
        self,
        ctx: CellContext,
        state: WidgetState,
        item: dict[str, Any],
        index: int,
        *,
        avail_w: float,
        text_px: float,
        label_px_row: float,
        bar_px: float,
        pct_w: float,
        text_css: str,
        label_css: str,
        value_shown: bool,
        labels_shown: bool,
    ) -> str:
        """One progress row: label + raw value over bar + percent."""
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
            # Accent-cycled per row so a stack of bars reads as a set.
            rgb = ctx.theme.get_accent_color(index)
        color = css_rgb(rgb) if rgb else "var(--primary)"

        value_text = f"{value:.0f}/{target:.0f}"
        if unit:
            value_text += f" {unit}"

        icon = item.get("icon")
        # Row icons are sized to the row's own type, not the kit's cell
        # scale, or they tower over the label they belong to.
        icon_html = (
            mdi_span(icon, "icon", f"font-size: {label_px_row * 1.25:.1f}px; color: {color}")
            if icon
            else ""
        )

        label_row = ""
        if labels_shown:
            budget = avail_w - pct_w * 0.2
            if icon_html:
                budget -= label_px_row * 1.7
            if value_shown:
                budget -= len(value_text) * label_px_row * char_em(ctx) + 6
            label_text = truncate_text(
                label.upper(), max(3, int(budget / (label_px_row * char_em(ctx, caps=True))))
            )
            # Label and raw value share one size so the line reads as a
            # pair; the percent below is the row's actual readout.
            raw = (
                f'<span class="hide-small" style="font-size: {label_px_row:.1f}px; '
                "font-weight: 600; line-height: 1; flex: none; "
                f'color: var(--text-secondary)">{escape(value_text)}</span>'
            )
            # .hide-short must sit on a wrapper: an inline display:flex
            # would win over the kit's media rule.
            label_row = (
                '<div class="hide-short">'
                '<div style="display: flex; align-items: center; gap: 5px">'
                f"{icon_html}"
                f'<span style="{label_css} flex: 1 1 0; min-width: 0">'
                f"{escape(label_text)}</span>"
                f"{raw}</div></div>"
            )

        bar = bar_html(percent, color=color, track=track_css(ctx, rgb), thickness=f"{bar_px:.1f}px")
        bar_row = (
            '<div style="display: flex; align-items: center; gap: 6px">'
            f'<div style="flex: 1 1 0; min-width: 0; display: flex">{bar}</div>'
            f'<span style="{text_css} flex: none; width: {pct_w:.0f}px; text-align: right">'
            f"{percent:.0f}%</span>"
            "</div>"
        )
        return (
            '<div style="flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; '
            f'justify-content: center; gap: {max(2.0, bar_px * 0.5):.0f}px">'
            f"{label_row}{bar_row}</div>"
        )
