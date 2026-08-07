"""Attribute list widget for GeekMagic displays."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..const import PLACEHOLDER_NAME, PLACEHOLDER_VALUE
from ..htmldoc import css_rgb
from ._cardfit import fit_caption_sized
from ._cellkit import cell_box_px, cell_padding, hairline_css
from ._textfit import TextMetrics, metrics_for
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

# Row labels are caps a step below the value. Their tracking is set
# explicitly (no theme can override an inline style), so it is also what
# they get measured at — unlike the title, which rides ``.t-label`` and
# has to assume the widest tracking any theme applies.
_ROW_TRACKING = 0.06

# Row pitch bounds, matching StatusListWidget so the two list widgets
# sit side by side without a visible change of rhythm.
_ROW_MIN = 10.5
_ROW_MAX = 46.0

# A row label gives up size before it gives up letters, down to this
# floor — "HUMIDITY" at 9px names its row, "HU…" at 13px does not.
_LABEL_MIN_PX = 9.0
# Characters that must survive truncation for a label to be worth the
# width ("AR…" is noise, "ARRI…" still says "arrives").
_LABEL_MIN_KEEP = 4


def _fit_label(tm: TextMetrics, label: str, px: float, avail: float) -> tuple[str, float]:
    """Shrink one row's label into ``avail``, truncating below the floor.

    Per row, not per widget: sizing every label off the widest one meant
    a single long attribute name stripped the captions off the whole
    table. An empty result means even a stub would say nothing, and the
    caller gives the row to its value.
    """
    unit = tm.width(label, 1.0, "bold", _ROW_TRACKING)
    if unit <= 0:  # pragma: no cover - labels default to the attr key
        return label, px
    px_fit = avail / unit
    if px_fit >= _LABEL_MIN_PX:
        return label, min(px, px_fit)
    fitted = tm.truncate(label, _LABEL_MIN_PX, avail, "bold", tracking=_ROW_TRACKING, min_chars=3)
    if fitted != label and len(fitted.rstrip("…")) < _LABEL_MIN_KEEP:
        return "", _LABEL_MIN_PX
    return fitted, _LABEL_MIN_PX


@dataclass(frozen=True)
class _Item:
    """One resolved label/value pair."""

    label: str
    value: str
    color: str | None


class AttributeListWidget(Widget):
    """Widget that displays a list of entity attributes as key-value pairs.

    A key/value table in the watchOS voice: tertiary caps label on the
    left, emphasized value right-aligned, hairline between rows, and an
    even pitch that stays a centred block rather than stretching two
    rows to opposite edges of a 240px cell.

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

    def _resolve_items(self, state: WidgetState) -> list[_Item]:
        """Read every configured attribute off the entity."""
        entity = state.entity
        # Per design system: list-row values default to text_primary —
        # they're "values", not gauge accents. Per-attribute config (or
        # config.color for the whole widget) can still tint a row.
        default_color = css_rgb(self.config.color) if self.config.color else None

        items: list[_Item] = []
        for attr_config in self.attributes:
            if isinstance(attr_config, dict):
                key = attr_config.get("key", "")
                label = attr_config.get("label", key)
                raw_color = attr_config.get("color")
                if isinstance(raw_color, list | tuple) and len(raw_color) == 3:
                    color = css_rgb(tuple(raw_color))
                else:
                    color = default_color
            else:
                # Simple string format: the attribute name is the label.
                key = str(attr_config)
                label = key
                color = default_color

            if entity is None:
                value = PLACEHOLDER_VALUE
            elif key == "state":
                # Special case: "state" refers to the entity state.
                value = entity.state
            else:
                value = self._format_value(entity.get(key))

            items.append(_Item(label=str(label), value=str(value), color=color))
        return items

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render key-value rows: caps label left, emphasized value right."""
        tm = metrics_for(ctx.theme)
        items = self._resolve_items(state)

        title = self.title
        if not self.attributes:
            # Nothing configured — the entity name is the whole message.
            entity = state.entity
            if not title and entity:
                title = entity.friendly_name
            elif not title:
                title = self.config.entity_id or PLACEHOLDER_NAME

        pad_x, pad_y = cell_padding(ctx)
        avail, usable_h = cell_box_px(ctx, pad_x, pad_y)
        count = max(1, len(items))

        title_text, title_px = fit_caption_sized(title, ctx, avail) if title else ("", 0.0)
        title_h = title_px * 1.9 if title_text else 0.0
        # The title answers to the row budget it displaces, never to the
        # cell width — a narrow column needs its heading too, and with
        # nothing configured the title IS the widget, so it always shows.
        show_title = bool(title_text) and (not items or (usable_h - title_h) / count >= _ROW_MIN)
        rows_h = usable_h - (title_h if show_title else 0.0)

        if items and rows_h / count < _ROW_MIN:
            items = items[: max(1, int(rows_h // _ROW_MIN))]
            count = len(items)
        row_h = min(rows_h / count, _ROW_MAX)

        value_px = max(10.0, min(row_h * 0.50, 24.0))
        gap = max(5.0, row_h * 0.16)
        item_label_px = self._label_size(tm, items, value_px, avail - gap)

        body = "".join(
            self._row_html(
                tm,
                item,
                index=i,
                row_h=row_h,
                label_px_=item_label_px,
                value_px=value_px,
                gap=gap,
                avail=avail,
                hairline=hairline_css(ctx.theme),
            )
            for i, item in enumerate(items)
        )

        title_html = ""
        if show_title:
            title_html = (
                '<div class="t-label" style="text-align: left; flex: none; '
                f"font-size: {title_px:.1f}px; "
                f'padding-bottom: {title_px * 0.55:.1f}px">{escape(title_text)}</div>'
            )

        return (
            f'<div class="cell" style="padding: {pad_y:.1f}px {pad_x:.1f}px; '
            'align-items: stretch; justify-content: center; text-align: left">'
            f"{title_html}"
            '<div style="flex: none; display: flex; flex-direction: column">'
            f"{body}</div></div>"
        )

    @staticmethod
    def _label_size(tm: TextMetrics, items: list[_Item], value_px: float, budget: float) -> float:
        """The size every row's label *starts* at.

        Labels are the cheap half of the row — a smaller caps label still
        reads as a caption — so this keeps the longest one whole in half
        the row where it can. Rows that still overflow shrink their own
        label from here (:func:`_fit_label`); one long attribute name no
        longer costs every other row its caption.
        """
        ideal = max(_LABEL_MIN_PX, min(value_px * 0.78, 14.0))
        if not items:
            return ideal
        widest = max(tm.width(i.label.upper(), 1.0, "bold", _ROW_TRACKING) for i in items)
        if widest <= 0:  # pragma: no cover - labels default to the attr key
            return ideal
        return max(_LABEL_MIN_PX, min(ideal, budget * 0.5 / widest))

    @staticmethod
    def _row_html(
        tm: TextMetrics,
        item: _Item,
        *,
        index: int,
        row_h: float,
        label_px_: float,
        value_px: float,
        gap: float,
        avail: float,
        hairline: str,
    ) -> str:
        """One label/value row with a hairline above every row but the first."""
        color_css = f" color: {item.color};" if item.color else ""
        sep = f"border-top: 1px solid {hairline}; " if index > 0 else ""
        row_open = (
            f'<div style="{sep}height: {row_h:.1f}px; flex: none; display: flex; '
            f'align-items: center; gap: {gap:.1f}px">'
        )
        value_css = (
            f"white-space: nowrap; font-size: {value_px:.1f}px; "
            f"font-weight: 700; line-height: 1.05;{color_css}"
        )

        # The value carries the information, so it is served first — but
        # the label only yields size, and only its own row's worth: it
        # shrinks toward the floor before it truncates, and truncates
        # before it goes.
        label = item.label.upper()
        value = item.value
        label_w = tm.width(label, label_px_, "bold", _ROW_TRACKING)
        value_w = tm.width(value, value_px, "bold")
        budget = avail - gap

        if label_w + value_w > budget:
            if value_w > budget * 0.78:
                # Pathologically long value — split the row.
                value = tm.truncate(
                    value, value_px, max(budget * 0.62, budget - label_w), "bold", min_chars=2
                )
                value_w = tm.width(value, value_px, "bold")
            label, label_px_ = _fit_label(tm, label, label_px_, budget - value_w)

        if not label:
            # Not even a stub of a caption fits — the value takes the
            # whole row rather than sitting next to a blank left edge.
            # Refitted from the original: the split above reserved room
            # for a label this row turns out not to have.
            value = tm.truncate(item.value, value_px, avail, "bold", min_chars=2)
            return (
                f"{row_open}"
                f'<span style="flex: 1; min-width: 0; text-align: center; {value_css}">'
                f"{escape(value)}</span></div>"
            )

        return (
            f"{row_open}"
            f'<span style="flex: 1; min-width: 0; white-space: nowrap; '
            f"font-size: {label_px_:.1f}px; font-weight: 700; line-height: 1.05; "
            f'letter-spacing: {_ROW_TRACKING}em; color: var(--text-tertiary)">'
            f"{escape(label)}</span>"
            f'<span style="flex: none; text-align: right; {value_css}">'
            f"{escape(value)}</span>"
            "</div>"
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
