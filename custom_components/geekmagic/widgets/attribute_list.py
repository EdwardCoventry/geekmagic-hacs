"""Attribute list widget for GeekMagic displays."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..const import PLACEHOLDER_NAME, PLACEHOLDER_VALUE
from ..htmldoc import css_rgb
from .base import Widget, WidgetConfig
from .helpers import truncate_text

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


class AttributeListWidget(Widget):
    """Widget that displays a list of entity attributes as key-value pairs.

    Configuration example:
        widget:
          type: attribute_list
          entity_id: sensor.bus_arrival
          options:
            title: "Bus Info"
            attributes:
              - key: route_name
                label: "Route"
              - key: destination
                label: "To"
              - key: state
                label: "Arrives"
    """

    WIDGET_TYPE: ClassVar[str] = "attribute_list"

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the attribute list widget."""
        super().__init__(config)
        self.attributes = config.options.get("attributes", [])
        self.title = config.options.get("title")

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render key-value rows in a flex column: label left, value right."""
        entity = state.entity

        # Per design system: list-row values default to text_primary
        # (white) — they're "values", not gauge accents. Per-attribute
        # config (or config.color for the whole widget) can still tint
        # individual rows.
        default_color = css_rgb(self.config.color) if self.config.color else None

        items: list[tuple[str, str, str | None]] = []
        for attr_config in self.attributes:
            # Support both dict format and simple string format
            if isinstance(attr_config, dict):
                key = attr_config.get("key", "")
                label = attr_config.get("label", key)
                item_color = attr_config.get("color")
                if isinstance(item_color, list | tuple) and len(item_color) == 3:
                    item_color = css_rgb(tuple(item_color))
                else:
                    item_color = default_color
            else:
                # Simple string format: use attribute name as both key and label
                key = str(attr_config)
                label = key
                item_color = default_color

            # Get value from entity
            if entity is None:
                value = PLACEHOLDER_VALUE
            elif key == "state":
                # Special case: "state" refers to entity state, not an attribute
                value = entity.state
            else:
                raw_value = entity.get(key)
                value = self._format_value(raw_value)

            items.append((label, value, item_color))

        # If no attributes configured, show friendly name as title
        title = self.title
        if not self.attributes:
            if not title and entity:
                title = entity.friendly_name
            elif not title:
                title = self.config.entity_id or PLACEHOLDER_NAME

        # Blitz has no text-overflow/flex-shrink text truncation, so
        # allocate label/value widths in Python (like the old
        # ``LabelValueRow``) from estimated character widths.
        vmin = min(ctx.width, ctx.height)
        value_px = max(11.0, min(19.0, 0.12 * vmin))
        label_px = max(10.0, min(17.0, 0.11 * vmin))
        value_cw = value_px * 0.58  # avg bold char width
        label_cw = label_px * 0.55
        gap = 6
        avail = ctx.width * 0.88 - gap  # cell padding is 6% each side

        rows: list[str] = []
        if title:
            # At narrow widths the title eats a row better spent on data.
            title_cw = label_px * 0.70  # caps + letter-spacing
            title_text = truncate_text(title.upper(), max(4, int((avail + gap) // title_cw)))
            rows.append(
                '<div class="t-label hide-narrow" style="text-align: left">'
                f"{escape(title_text)}</div>"
            )

        # Row text scales with the cell but stays list-sized (several
        # rows share the cell). Values are bolder than labels.
        label_css = (
            "flex: 1 1 0; min-width: 0; text-align: left; color: var(--text-secondary); "
            f"font-size: {label_px:.1f}px; font-weight: 600; line-height: 1.2;"
        )
        value_css = (
            f"white-space: nowrap; font-weight: 700; line-height: 1.2; font-size: {value_px:.1f}px;"
        )

        for raw_label, raw_value, color in items:
            label, value = str(raw_label), str(raw_value)
            label_w = len(label) * label_cw
            value_w = len(value) * value_cw

            if label_w + value_w <= avail:
                pass  # everything fits
            elif value_w >= ctx.width * 0.7:
                # Drop the label entirely if the value alone barely fits —
                # the value carries the actual information, and "Arr… 5 m…"
                # is worse than just "5 min".
                label = ""
                value = truncate_text(value, max(2, int((avail + gap) // value_cw)))
            elif value_w <= avail:
                # Value fits in full; give the rest to a truncated label.
                label = truncate_text(label, max(1, int((avail - value_w) // label_cw)))
            else:
                # Value doesn't fit either — value gets 60%, label 40%.
                value_max = max(avail * 0.60, avail - label_w)
                label = truncate_text(label, max(1, int((avail - value_max) // label_cw)))
                value = truncate_text(value, max(2, int(value_max // value_cw)))

            color_css = f" color: {color};" if color else ""
            label_html = f'<span style="{label_css}">{escape(label)}</span>' if label else ""
            rows.append(
                f'<div style="display: flex; align-items: center; gap: {gap}px">'
                f"{label_html}"
                f'<span style="{value_css}{color_css}">{escape(value)}</span>'
                "</div>"
            )

        return (
            '<div class="cell" style="align-items: stretch; padding: 5% 6%; gap: 2px">'
            f"{''.join(rows)}</div>"
        )

    def _format_value(self, value: Any) -> str:
        """Format attribute value for display."""
        if value is None:
            return PLACEHOLDER_VALUE
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, float):
            # Format floats with reasonable precision
            return str(int(value)) if value == int(value) else f"{value:.1f}"
        if isinstance(value, list):
            return f"[{len(value)} items]"
        if isinstance(value, dict):
            return f"{{{len(value)} keys}}"
        return str(value)
