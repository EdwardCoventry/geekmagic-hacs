"""Status widget for GeekMagic displays."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..const import PLACEHOLDER_NAME
from ..htmldoc import css_rgb, css_rgba, mdi_span
from ._textfit import fit_font_size, text_width, truncate_to_width
from .base import Widget, WidgetConfig
from .helpers import (
    ON_STATES,
    get_binary_sensor_icon,
    get_domain_state_icon,
    translate_binary_state,
)

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import EntityState, WidgetState

# Kit typography constants mirrored in Python so bands can be measured
# before they are emitted (Blitz never clips text for us).
_HERO_TRACKING = -0.035  # .t-hero letter-spacing, em
_LABEL_TRACKING = 0.14  # .t-label letter-spacing, em

# Indicator chip: the icon sits in a soft lozenge tinted with the state
# colour — an iOS status-tile lamp. Sizes are em-relative to the icon's
# own font-size, so the chip scales with whatever the kit picks.
# MDI glyphs carry generous internal padding, so the lozenge only needs
# a little more than the em box to look optically centred.
_CHIP_SIZE_EM = 1.38
_CHIP_FILL_ALPHA = 0.17
_CHIP_RING_ALPHA = 0.26
# Same tint, used to fill the state pills in the list variant.
_PILL_FILL_ALPHA = 0.16


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


def _tint_rgb(value: object, ctx: CellContext, role: str) -> tuple[int, int, int]:
    """Resolve a state colour to concrete RGB for rgba() tints.

    ``var(--success)`` cannot be faded with ``rgba()``, so the halo behind
    the icon needs real channel values: the user's configured colour when
    there is one, otherwise the active theme's semantic role.
    """
    if isinstance(value, list | tuple) and len(value) == 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            pass
    theme = ctx.theme
    if theme is None:  # pragma: no cover - ctx always carries a theme
        return (128, 128, 128)
    return getattr(theme, role)


def _chip_html(icon: str, color: str, tint: tuple[int, int, int], *, size_class: str, px: float | None = None) -> str:
    """Icon inside a tinted indicator lozenge.

    ``px`` overrides the kit size class when the band has a measured
    height budget; otherwise the class (``i-lg``/``i-md``) drives it and
    the chip follows in ``em``.
    """
    style = [
        f"color: {color}",
        f"background: {css_rgba(tint, _CHIP_FILL_ALPHA)}",
        f"border: 1px solid {css_rgba(tint, _CHIP_RING_ALPHA)}",
        f"width: {_CHIP_SIZE_EM}em",
        f"height: {_CHIP_SIZE_EM}em",
        "display: inline-flex",
        "align-items: center",
        "justify-content: center",
        "border-radius: 999px",
        "box-sizing: border-box",
        "flex: none",
    ]
    if px is not None:
        style.insert(0, f"font-size: {px:.1f}px")
    return mdi_span(icon, f"icon {size_class}", "; ".join(style))


def _label_px(ctx: CellContext) -> float:
    """The size the kit's ``.t-label`` resolves to for this cell."""
    return max(10.0, min(0.10 * min(ctx.width, ctx.height), 0.075 * ctx.width, 15.0))


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

    Reads as a physical indicator: the device icon sits in a lozenge
    tinted with the state colour (iOS status tile), and the ON/OFF hero
    carries the same tint — the documented exception where colour *is*
    the meaning.

    Three layouts, chosen from the cell's aspect at render time:

    - **strip** (wide and short): chip on the left, name + state stacked
      beside it, so a 228x74 slot spends its width instead of its height.
    - **stack** (square-ish and roomy): chip / name / state bands.
    - **compact** (either side under ~90px): state only, sized as large
      as the cell allows.
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
        self._on_option = config.options.get("on_color")
        self._off_option = config.options.get("off_color")
        self.on_color = _css_color(self._on_option, "var(--success)")
        self.off_color = _css_color(self._off_option, "var(--error)")
        self.on_text = config.options.get("on_text", "ON")
        self.off_text = config.options.get("off_text", "OFF")
        self.icon = config.options.get("icon")
        self.show_status_text = config.options.get("show_status_text", True)

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the status widget."""
        entity = state.entity
        is_on = _is_entity_on(entity)
        color = self.on_color if is_on else self.off_color
        tint = _tint_rgb(
            self._on_option if is_on else self._off_option,
            ctx,
            "success" if is_on else "error",
        )
        status_text = self.on_text if is_on else self.off_text
        name = self.label_for(entity, fallback=PLACEHOLDER_NAME)
        icon = self.icon or _entity_status_icon(entity) or "circle"

        if not self.show_status_text:
            return self._render_icon_only(ctx, name, icon, color, tint)

        # Wide slots read far better as a row: the chip anchors the left
        # edge and the name/state stack spends the width instead of
        # stranding it either side of a centred column.
        if ctx.width >= 150 and ctx.width >= ctx.height * 1.7:
            return self._render_strip(ctx, name, icon, color, tint, status_text)
        if min(ctx.width, ctx.height) < 90:
            return self._render_compact(ctx, color, status_text)
        return self._render_stack(ctx, name, icon, color, tint, status_text)

    # ------------------------------------------------------------------
    # Layouts
    # ------------------------------------------------------------------

    def _caption_html(
        self, text: str, px: float, max_width: float, align: str, *, hide_short: bool = True
    ) -> str:
        """A caps-tracked name band, truncated to the width it actually has."""
        fitted = truncate_to_width(
            text.upper(), px, max_width, "bold", tracking=_LABEL_TRACKING, min_chars=3
        )
        classes = "t-label hide-short" if hide_short else "t-label"
        return f'<div class="{classes}" style="text-align: {align}">{escape(fitted)}</div>'

    def _render_stack(
        self,
        ctx: CellContext,
        name: str,
        icon: str,
        color: str,
        tint: tuple[int, int, int],
        status_text: str,
    ) -> str:
        """Chip / name / state, spread evenly down the cell."""
        usable_h = ctx.height * 0.92
        usable_w = ctx.width * 0.92
        caption_px = _label_px(ctx)

        chip_outer = min(max(0.36 * usable_h, 26.0), 104.0, 0.55 * usable_w)
        hero_px = fit_font_size(
            status_text,
            usable_w * 0.94,
            0.38 * usable_h,
            "extrabold",
            tracking=_HERO_TRACKING,
            min_px=14.0,
        )
        # Short values leave the height budget unspent — give the slack
        # back to the indicator so the cell never reads half-empty.
        slack = usable_h - (chip_outer + caption_px * 1.2 + hero_px)
        if slack > 0.22 * usable_h:
            chip_outer = min(chip_outer + slack * 0.45, 104.0, 0.55 * usable_w)

        chip = _chip_html(icon, color, tint, size_class="i-md", px=chip_outer / _CHIP_SIZE_EM)
        return (
            '<div class="cell">'
            f'<div class="card-icon hide-short">{chip}</div>'
            f"{self._caption_html(name, caption_px, usable_w, 'center')}"
            f'<div class="t-hero" style="color: {color}; font-size: {hero_px:.1f}px">'
            f"{escape(status_text)}</div>"
            "</div>"
        )

    def _render_strip(
        self,
        ctx: CellContext,
        name: str,
        icon: str,
        color: str,
        tint: tuple[int, int, int],
        status_text: str,
    ) -> str:
        """Chip on the left, name over state on the right."""
        usable_h = ctx.height * 0.92
        usable_w = ctx.width * 0.92
        caption_px = _label_px(ctx)

        chip_outer = min(max(0.60 * usable_h, 24.0), 104.0, 0.34 * usable_w)
        gap = max(7.0, chip_outer * 0.20)
        text_w = usable_w - chip_outer - gap
        inner_gap = max(2.0, usable_h * 0.05)
        hero_px = fit_font_size(
            status_text,
            text_w,
            usable_h - caption_px * 1.15 - inner_gap,
            "extrabold",
            tracking=_HERO_TRACKING,
            min_px=14.0,
        )

        chip = _chip_html(icon, color, tint, size_class="i-md", px=chip_outer / _CHIP_SIZE_EM)
        return (
            f'<div class="cell row" style="justify-content: center; gap: {gap:.1f}px">'
            f"{chip}"
            '<div style="display: flex; flex-direction: column; align-items: flex-start; '
            f'justify-content: center; gap: {inner_gap:.1f}px">'
            f"{self._caption_html(name, caption_px, text_w, 'left', hide_short=False)}"
            f'<div class="t-hero" style="color: {color}; font-size: {hero_px:.1f}px">'
            f"{escape(status_text)}</div>"
            "</div></div>"
        )

    def _render_compact(self, ctx: CellContext, color: str, status_text: str) -> str:
        """3x3-grid slot: the state, as big as the cell allows."""
        hero_px = fit_font_size(
            status_text,
            ctx.width * 0.90,
            ctx.height * 0.62,
            "extrabold",
            tracking=_HERO_TRACKING,
            min_px=12.0,
        )
        return (
            '<div class="cell" style="justify-content: center">'
            f'<div class="t-hero" style="color: {color}; font-size: {hero_px:.1f}px">'
            f"{escape(status_text)}</div></div>"
        )

    def _render_icon_only(
        self,
        ctx: CellContext,
        name: str,
        icon: str,
        color: str,
        tint: tuple[int, int, int],
    ) -> str:
        """The tinted chip *is* the state — promoted to the hero band."""
        usable_h = ctx.height * 0.92
        usable_w = ctx.width * 0.92
        caption_px = _label_px(ctx)
        show_caption = ctx.height >= 100
        chip_outer = min(
            usable_h - (caption_px * 1.9 if show_caption else 0.0),
            usable_w * 0.72,
            132.0,
        )
        chip = _chip_html(
            icon, color, tint, size_class="i-lg", px=max(14.0, chip_outer / _CHIP_SIZE_EM)
        )
        caption = (
            self._caption_html(name, caption_px, usable_w, "center", hide_short=False)
            if show_caption
            else ""
        )
        return f'<div class="cell">{caption}<div class="card-icon">{chip}</div></div>'


class StatusListWidget(Widget):
    """Widget that displays a list of binary sensors with status indicators.

    watchOS list pattern: caps-tracked title, then evenly-pitched rows
    separated by hairlines. Each row is a fixed-width icon column (so
    names start on a common left edge), the name, and the state in a
    small pill tinted with the state colour. Rows keep a maximum pitch,
    so a two-item list in a 240px cell stays a tight centred block
    instead of two items marooned at opposite edges.
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

    # Row pitch bounds. The floor keeps 10px names legible on a 2" panel;
    # the ceiling stops short lists from sprawling across a big cell.
    _ROW_MIN = 15.0
    _ROW_MAX = 46.0

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the status list widget."""
        super().__init__(config)
        self.entities = config.options.get("entities", [])
        self._on_option = config.options.get("on_color")
        self._off_option = config.options.get("off_color")
        self.on_color = _css_color(self._on_option, "var(--success)")
        self.off_color = _css_color(self._off_option, "var(--error)")
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
        entries = list(self.entities) or [None]
        count = len(entries)

        caption_px = _label_px(ctx)
        usable_h = ctx.height * 0.90
        usable_w = ctx.width * 0.88

        # The title only earns its band when the rows it displaces would
        # still be legible without it.
        title_h = caption_px * 1.9
        show_title = bool(self.title) and (usable_h - title_h) / count >= self._ROW_MIN
        rows_h = usable_h - (title_h if show_title else 0.0)

        row_h = max(min(rows_h / count, self._ROW_MAX), self._ROW_MIN)
        name_px = max(10.0, min(row_h * 0.50, 20.0))
        icon_px = max(11.0, min(row_h * 0.58, 22.0))
        icon_col = icon_px * 1.25
        gap = max(4.0, name_px * 0.32)
        pill_px = max(9.0, min(name_px * 0.74, 14.0))

        rows = [
            self._row_html(
                ctx,
                state,
                entry,
                index=i,
                row_h=row_h,
                name_px=name_px,
                icon_px=icon_px,
                icon_col=icon_col,
                gap=gap,
                pill_px=pill_px,
                avail=usable_w,
            )
            for i, entry in enumerate(entries)
        ]

        title_html = ""
        if show_title and self.title:
            fitted = truncate_to_width(
                self.title.upper(),
                caption_px,
                usable_w,
                "bold",
                tracking=_LABEL_TRACKING,
                min_chars=3,
            )
            title_html = (
                '<div class="t-label" style="text-align: left; flex: none; '
                f'padding-bottom: {caption_px * 0.55:.1f}px">{escape(fitted)}</div>'
            )

        return (
            '<div class="cell" style="padding: 5% 6%; align-items: stretch; '
            'justify-content: center; text-align: left">'
            f"{title_html}"
            '<div style="flex: none; display: flex; flex-direction: column">'
            f"{''.join(rows)}</div></div>"
        )

    def _row_html(
        self,
        ctx: CellContext,
        state: WidgetState,
        entry: Any,
        *,
        index: int,
        row_h: float,
        name_px: float,
        icon_px: float,
        icon_col: float,
        gap: float,
        pill_px: float,
        avail: float,
    ) -> str:
        """One list row: icon column, name, tinted state pill."""
        if isinstance(entry, list | tuple):
            entity_id, label = entry[0], entry[1]
        elif entry is None:
            entity_id, label = "", PLACEHOLDER_NAME
        else:
            entity_id, label = entry, None

        entity = state.get_entity(entity_id) if entity_id else None
        is_on = _is_entity_on(entity)
        color = self.on_color if is_on else self.off_color
        tint = _tint_rgb(
            self._on_option if is_on else self._off_option,
            ctx,
            "success" if is_on else "error",
        )
        if entity and not label:
            label = entity.friendly_name
        label = str(label or entity_id or PLACEHOLDER_NAME)

        icon = _entity_status_icon(entity)
        if icon:
            lead = mdi_span(
                icon,
                "icon",
                f"font-size: {icon_px:.1f}px; color: {color}; flex: none; "
                f"width: {icon_col:.1f}px; text-align: center",
            )
        else:
            # No icon known — a tinted lamp still reads as a status.
            dot = max(6.0, icon_px * 0.5)
            lead = (
                f'<span style="flex: none; width: {icon_col:.1f}px; display: flex; '
                'align-items: center; justify-content: center">'
                f'<span style="width: {dot:.1f}px; height: {dot:.1f}px; '
                f'border-radius: 50%; background: {color}"></span></span>'
            )

        state_text = self._state_text(entity, is_on)
        # A pill only goes in when the name keeps a readable share of the
        # row; below that the tinted icon carries the state on its own.
        pill_w = text_width(state_text, pill_px, "bold") + pill_px * 1.7
        name_budget = avail - icon_col - gap
        pill_html = ""
        if name_budget - pill_w - gap >= name_px * 4.6:
            name_budget -= pill_w + gap
            pill_html = (
                f'<span class="chip" style="flex: none; font-size: {pill_px:.1f}px; '
                f"font-weight: 700; color: {color}; "
                f'background: {css_rgba(tint, _PILL_FILL_ALPHA)}">{escape(state_text)}</span>'
            )

        display_label = truncate_to_width(label, name_px, name_budget, "semibold", min_chars=3)
        sep = (
            f"border-top: 1px solid var(--hairline); " if index > 0 else ""
        )
        return (
            f'<div style="{sep}height: {row_h:.1f}px; flex: none; display: flex; '
            f'align-items: center; gap: {gap:.1f}px">'
            f"{lead}"
            f'<span style="flex: 1; min-width: 0; font-size: {name_px:.1f}px; '
            'font-weight: 600; line-height: 1.15; white-space: nowrap; '
            f'color: var(--text-primary)">{escape(display_label)}</span>'
            f"{pill_html}"
            "</div>"
        )
