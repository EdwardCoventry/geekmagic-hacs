"""Status widget for GeekMagic displays."""

from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from PIL import ImageFont

from ..const import PLACEHOLDER_NAME
from ..htmldoc import css_rgb, mdi_span
from ._card import card_html
from .base import Widget, WidgetConfig
from .helpers import (
    ON_STATES,
    get_binary_sensor_icon,
    get_domain_state_icon,
    translate_binary_state,
    truncate_text,
)

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import EntityState, WidgetState


def _is_entity_on(entity: EntityState | None) -> bool:
    """Check if entity is in 'on' state."""
    if entity is None:
        return False
    return entity.state.lower() in ON_STATES


def _css_color(value: object, fallback: str) -> str:
    """Coerce a stored RGB option (JSON list/tuple) to CSS, else a palette var."""
    if isinstance(value, list | tuple) and len(value) == 3:
        try:
            return css_rgb((int(value[0]), int(value[1]), int(value[2])))
        except (TypeError, ValueError):
            return fallback
    return fallback


_FONTS_DIR = Path(__file__).parent.parent / "fonts"


@lru_cache(maxsize=64)
def _measure_font(px: int, bold: bool = False) -> ImageFont.FreeTypeFont | None:
    """Load the embedded Nunito font at a pixel size for width measurement."""
    name = "Nunito-Bold.ttf" if bold else "Nunito-SemiBold.ttf"
    try:
        return ImageFont.truetype(str(_FONTS_DIR / name), px)
    except OSError:
        return None


def _text_width(text: str, px: int, bold: bool = False) -> float:
    """Measure rendered text width in px (estimate if the font is missing)."""
    font = _measure_font(px, bold)
    if font is None:
        return len(text) * px * 0.55
    return font.getlength(text)


def _truncate_to_width(text: str, px: int, max_width: float) -> str:
    """Middle-truncate text until it fits max_width at the given font size.

    Blitz does not draw the CSS ``text-overflow`` ellipsis, so names are
    truncated Python-side using real font metrics.
    """
    if _text_width(text, px) <= max_width:
        return text
    for n in range(len(text) - 1, 4, -1):
        candidate = truncate_text(text, n, style="middle")
        if _text_width(candidate, px) <= max_width:
            return candidate
    return truncate_text(text, 4, style="middle")


def _entity_status_icon(entity: EntityState | None) -> str | None:
    """Derive an icon for an entity: device_class state icon > explicit icon > domain icon."""
    if entity is None:
        return None
    domain = entity.entity_id.split(".")[0]
    if domain == "binary_sensor":
        icon = get_binary_sensor_icon(entity.state, entity.device_class)
        if icon:
            return icon
    if entity.icon:
        return entity.icon
    return get_domain_state_icon(domain, entity.state, entity.device_class)


class StatusWidget(Widget):
    """Widget that displays a binary sensor status with colored indicator.

    Per the watchOS contract, the icon's tint and the hero text colour
    both carry the state: success (green) when the entity is on, error
    (red) when off. Uses the three-band card: name caption, feature
    icon, big ON/OFF hero — bands drop automatically in compact cells.
    """

    WIDGET_TYPE: ClassVar[str] = "status"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Status",
        "needs_entity": True,
        "entity_domains": None,  # Any entity (interprets state as on/off)
        "options": [
            {"key": "on_text", "type": "text", "label": "On Text", "default": "On"},
            {"key": "off_text", "type": "text", "label": "Off Text", "default": "Off"},
            {
                "key": "on_color",
                "type": "color",
                "label": "On Color",
                "default": [102, 166, 30],
            },
            {
                "key": "off_color",
                "type": "color",
                "label": "Off Color",
                "default": [231, 76, 60],
            },
            {"key": "icon", "type": "icon", "label": "Icon"},
            {
                "key": "show_status_text",
                "type": "boolean",
                "label": "Show Status Text",
                "default": True,
            },
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the status widget."""
        super().__init__(config)
        self.on_color = _css_color(config.options.get("on_color"), "var(--success)")
        self.off_color = _css_color(config.options.get("off_color"), "var(--error)")
        self.on_text = config.options.get("on_text", "ON")
        self.off_text = config.options.get("off_text", "OFF")
        self.icon = config.options.get("icon")
        self.show_status_text = config.options.get("show_status_text", True)

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the status widget."""
        entity = state.entity
        is_on = _is_entity_on(entity)
        color = self.on_color if is_on else self.off_color
        status_text = self.on_text if is_on else self.off_text
        name = self.label_for(entity, fallback=PLACEHOLDER_NAME)
        icon = self.icon or _entity_status_icon(entity)

        if not self.show_status_text:
            # Icon-only mode: the tinted icon IS the state — promote it
            # to the hero band so it stays visible in compact cells.
            hero = mdi_span(icon or "circle", "icon i-lg", f"color: {color}")
            return card_html(caption=name, hero=hero, hero_is_html=True)

        return card_html(
            caption=name,
            icon=icon,
            icon_color=color,
            icon_role="feature",
            hero=status_text,
            hero_color=color,
        )


class StatusListWidget(Widget):
    """Widget that displays a list of binary sensors with status indicators.

    watchOS list pattern: caps-tracked title, tinted icon (or dot) per
    row, semibold name on the left, tinted state on the right, thin
    separator lines between rows. Rows flex to share the cell height;
    the title and right-hand state text drop in compact cells.
    """

    WIDGET_TYPE: ClassVar[str] = "status_list"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Status List",
        "needs_entity": False,
        "options": [
            {"key": "title", "type": "text", "label": "Title"},
            {"key": "entities", "type": "status_entities", "label": "Status Entities"},
            {
                "key": "on_color",
                "type": "color",
                "label": "On Color",
                "default": [102, 166, 30],
            },
            {
                "key": "off_color",
                "type": "color",
                "label": "Off Color",
                "default": [231, 76, 60],
            },
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the status list widget."""
        super().__init__(config)
        self.entities = config.options.get("entities", [])
        self.on_color = _css_color(config.options.get("on_color"), "var(--success)")
        self.off_color = _css_color(config.options.get("off_color"), "var(--error)")
        self.on_text = config.options.get("on_text")
        self.off_text = config.options.get("off_text")
        self.title = config.options.get("title")

    def get_entities(self) -> list[str]:
        """Return list of entity IDs this widget depends on."""
        return [e[0] if isinstance(e, list | tuple) else e for e in self.entities]

    def _state_text(self, entity: EntityState | None, is_on: bool) -> str:
        """Right-hand state text: configured on/off text > device_class translation."""
        configured = self.on_text if is_on else self.off_text
        if configured:
            return configured
        if entity is not None and entity.entity_id.startswith("binary_sensor."):
            translated = translate_binary_state(entity.state, entity.device_class)
            if translated != entity.state:
                return translated
        return "On" if is_on else "Off"

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the status list widget."""
        count = max(1, len(self.entities))

        # Scale row typography from the per-row height budget (CSS can't
        # know the row count, so this stays a Python calculation).
        title_frac = 0.16 if (self.title and not ctx.is_compact) else 0.0
        row_h = ctx.height * (0.92 - title_frac) / count
        name_px = max(9, min(22, round(row_h * 0.42)))
        icon_px = max(10, min(26, round(row_h * 0.55)))
        gap_px = max(3, name_px // 3)

        rows: list[str] = []
        for i, entry in enumerate(self.entities):
            if isinstance(entry, list | tuple):
                entity_id, label = entry[0], entry[1]
            else:
                entity_id = entry
                label = None

            entity = state.get_entity(entity_id)
            is_on = _is_entity_on(entity)
            color = self.on_color if is_on else self.off_color
            if entity and not label:
                label = entity.friendly_name
            label = label or entity_id

            icon = _entity_status_icon(entity)
            if icon:
                lead = mdi_span(icon, "icon", f"font-size: {icon_px}px; color: {color}; flex: none")
            else:
                # No icon known — fall back to a tinted status dot.
                dot = max(6, icon_px // 2)
                lead = (
                    f'<span style="flex: none; width: {dot}px; height: {dot}px; '
                    f'border-radius: 50%; background: {color}"></span>'
                )

            state_text = self._state_text(entity, is_on)

            # Truncate the name in Python using real font metrics
            # (CSS overflow stays as a backstop).
            show_state = ctx.width >= 100
            state_w = _text_width(state_text, name_px, bold=True) if show_state else 0
            name_budget = ctx.width * 0.86 - icon_px - gap_px * 2 - state_w
            display_label = _truncate_to_width(str(label), name_px, name_budget)

            sep = "border-top: 1px solid var(--border); " if i > 0 else ""
            rows.append(
                f'<div style="{sep}flex: 1; min-height: 0; display: flex; '
                f'align-items: center; gap: {gap_px}px">'
                f"{lead}"
                f'<span style="flex: 1; min-width: 0; overflow: hidden; '
                f"text-overflow: ellipsis; white-space: nowrap; text-align: left; "
                f'font-size: {name_px}px; font-weight: 600; color: var(--text-primary)">'
                f"{escape(display_label)}</span>"
                f'<span class="hide-narrow" style="flex: none; white-space: nowrap; '
                f'font-size: {name_px}px; font-weight: 700; color: {color}">'
                f"{escape(state_text)}</span>"
                f"</div>"
            )

        title_html = (
            f'<div class="t-label hide-short" style="text-align: left; flex: none">'
            f"{escape(self.title.upper())}</div>"
            if self.title
            else ""
        )
        return (
            '<div class="cell" style="padding: 4% 7%; align-items: stretch; '
            'justify-content: center; gap: 2%; text-align: left; overflow: hidden">'
            f"{title_html}"
            '<div style="flex: 1; min-height: 0; display: flex; flex-direction: column">'
            f"{''.join(rows)}</div></div>"
        )
