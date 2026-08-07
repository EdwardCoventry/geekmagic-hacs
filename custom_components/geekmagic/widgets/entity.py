"""Entity widget for GeekMagic displays."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from ..const import (
    PLACEHOLDER_NAME,
    PLACEHOLDER_VALUE,
)
from ..htmldoc import css_rgb
from ._card import card_html
from ._cardfit import (
    HERO_LINE,
    HERO_SHARE_SOLO,
    HERO_SHARE_STACKED,
    caption_visible,
    cell_box,
    fit_caption,
    fit_hero,
    hero_block,
    label_px,
)
from .base import Widget, WidgetConfig
from .helpers import get_binary_sensor_icon, translate_binary_state

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

# The feature icon reads as the cell's identifier, not its message: half
# the hero keeps the value unmistakably first (watchOS complication
# proportions).
_ICON_RATIO = 0.5
_ICON_MIN_PX = 13.0
_MAX_HERO_PX = 124.0
_MIN_HERO_PX = 12.0

# A hero that is width-bound in a tall cell can leave nearly half the
# height unspent; hand some of that slack to the icon rather than draw a
# cell that reads half-empty. Capped well under the hero so the value
# stays the biggest thing in the cell.
_SLACK_TRIGGER = 0.42
_SLACK_SHARE = 0.35
_ICON_RATIO_MAX = 0.70

# Only wrap a value onto two lines in cells with room to spare.
_WRAP_MIN_CELL = 130


def _get_entity_icon(entity_state) -> str | None:
    """Get icon from entity state, handling MDI format and state-specific icons."""
    if entity_state is None:
        return None

    # For binary sensors, get state-specific icon
    if entity_state.entity_id.startswith("binary_sensor."):
        icon = get_binary_sensor_icon(entity_state.state, entity_state.device_class)
        if icon:
            return icon.removeprefix("mdi:")

    # Check explicit icon attribute
    icon = entity_state.icon
    if icon and icon.startswith("mdi:"):
        return icon.removeprefix("mdi:")
    return None


class EntityWidget(Widget):
    """Widget that displays a Home Assistant entity state."""

    WIDGET_TYPE: ClassVar[str] = "entity"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Entity",
        "needs_entity": True,
        "entity_domains": None,  # All domains
        "options": [
            {"key": "show_name", "type": "boolean", "label": "Show Name", "default": True},
            {"key": "show_unit", "type": "boolean", "label": "Show Unit", "default": True},
            {"key": "show_icon", "type": "boolean", "label": "Show Icon", "default": True},
            {"key": "icon", "type": "icon", "label": "Icon Override"},
            {
                "key": "precision",
                "type": "number",
                "label": "Decimal Places",
                "min": 0,
                "max": 5,
            },
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the entity widget."""
        super().__init__(config)
        self.show_name = config.options.get("show_name", True)
        self.show_unit = config.options.get("show_unit", True)
        self.show_icon = config.options.get("show_icon", True)
        self.icon = config.options.get("icon")  # Explicit icon override
        self.precision = config.options.get("precision")  # Decimal places for numeric values
        # Attribute to read value from (instead of state)
        self.attribute = config.options.get("attribute")

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the entity widget."""
        entity = state.entity

        if entity is None:
            value = PLACEHOLDER_VALUE
            unit = ""
            name = self.label_for(None, fallback=self.config.entity_id or PLACEHOLDER_NAME)
        else:
            # Get value from attribute or state
            if self.attribute:
                raw_value = entity.get(self.attribute)
                value = str(raw_value) if raw_value is not None else PLACEHOLDER_VALUE
            else:
                value = entity.state
                if entity.entity_id.startswith("binary_sensor."):
                    value = translate_binary_state(value, entity.device_class)
                elif isinstance(value, str) and value.isalpha() and len(value) <= 16:
                    # Title-case short alpha flag states ('on'→'On', 'home'→'Home')
                    # to match binary-sensor 'Open'/'Closed' style.
                    value = value.title()
            # Apply precision formatting if specified and value is numeric
            if self.precision is not None:
                try:
                    numeric_value = float(value)
                    value = f"{numeric_value:.{self.precision}f}"
                except (ValueError, TypeError):
                    pass  # Keep original value if not numeric
            unit = entity.unit if self.show_unit else ""
            name = self.label_for(entity)

        # Determine icon to use
        icon = self.icon
        if not icon and self.show_icon:
            icon = _get_entity_icon(entity)

        box_w, box_h = cell_box(ctx)
        # "--" is the absence of a value, not a value: it reads as a
        # dimmed marker rather than a headline set in 100px dashes.
        missing = value == PLACEHOLDER_VALUE
        bands_kept = caption_visible(ctx)
        show_caption = bool(name) and self.show_name and bands_kept
        show_icon = bool(icon) and bands_kept

        caption_band = label_px(ctx) * 1.25 if show_caption else 0.0
        share = HERO_SHARE_SOLO if not (show_caption or show_icon) else HERO_SHARE_STACKED
        free_h = box_h - caption_band

        max_hero = min(_MAX_HERO_PX, 0.34 * box_h) if missing else _MAX_HERO_PX

        # Size the icon off the width-limited hero, then let it take its
        # share of the height back out of the hero's budget.
        loose = fit_hero(value, ctx, box_w, box_h * 4, suffix=unit, max_px=max_hero)
        icon_px = min(max(_ICON_RATIO * loose.px, _ICON_MIN_PX), 0.32 * box_h, 0.5 * box_w)

        hero = fit_hero(
            value,
            ctx,
            box_w,
            max(16.0, (free_h - (icon_px if show_icon else 0.0)) * share),
            suffix=unit,
            allow_wrap=min(ctx.width, ctx.height) >= _WRAP_MIN_CELL,
            max_px=max_hero,
            min_px=_MIN_HERO_PX,
        )

        icon_px = min(icon_px, max(_ICON_RATIO * hero.px, _ICON_MIN_PX))
        slack = free_h - (icon_px + hero.px * HERO_LINE)
        if slack > _SLACK_TRIGGER * free_h:
            icon_px = min(icon_px + _SLACK_SHARE * slack, 0.42 * box_w, _ICON_RATIO_MAX * hero.px)

        # card_html applies icon_color verbatim as the icon's inline
        # style, so the fitted size rides along with the colour.
        tint = css_rgb(self.config.color) if self.config.color else ctx.accent()
        icon_css = f"{tint}; font-size: {icon_px:.0f}px"

        return card_html(
            caption=fit_caption(name, ctx, box_w) if show_caption else None,
            icon=icon,
            icon_color=icon_css,
            # The entity icon is the cell's primary visual identifier —
            # promote it to its own band.
            icon_role="feature",
            hero=hero_block(hero, suffix=unit),
            hero_color="var(--text-tertiary)" if missing else None,
            hero_is_html=True,
            ctx=ctx,
        )
