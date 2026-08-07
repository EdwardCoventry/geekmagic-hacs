"""Text widget for GeekMagic displays."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb
from ._card import card_html
from ._cardfit import (
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

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

_MAX_HERO_PX = 124.0
_MIN_HERO_PX = 12.0

# Below this the cell has no room for a second line.
_WRAP_MIN_CELL = 100


class TextWidget(Widget):
    """Widget that displays static or dynamic text via the card pattern.

    Maps to ``card_html(caption=label, hero=text)`` — the watchOS
    caption-above-hero pattern. The hero is measured and fitted to the
    cell, so the legacy ``size`` option (small/regular/large/xlarge) is
    no longer needed and is silently ignored if present in stored
    configs. Likewise the legacy ``align`` option is ignored — text is
    centred in the watchOS contract. Sentences too long for one line
    take a second one rather than shrinking to nothing.
    """

    WIDGET_TYPE: ClassVar[str] = "text"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Text",
        "needs_entity": False,
        "options": [
            {"key": "text", "type": "text", "label": "Text Content"},
            {"key": "entity_id", "type": "entity", "label": "Entity (dynamic text)"},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the text widget."""
        super().__init__(config)
        self.text = config.options.get("text", "")
        # Entity ID for dynamic text (from options, takes precedence over widget entity_id)
        self.dynamic_entity_id = config.options.get("entity_id")

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the text widget."""
        text = self._get_text(state)
        box_w, box_h = cell_box(ctx)
        show_caption = bool(self.config.label) and caption_visible(ctx)
        caption_band = label_px(ctx) * 1.25 if show_caption else 0.0
        share = HERO_SHARE_STACKED if show_caption else HERO_SHARE_SOLO

        hero = fit_hero(
            text,
            ctx,
            box_w,
            max(16.0, (box_h - caption_band) * share),
            allow_wrap=min(ctx.width, ctx.height) >= _WRAP_MIN_CELL,
            # A tall column would otherwise strand its height below two
            # short lines; a wide cell reads better in two.
            max_lines=3 if box_h > 1.5 * box_w else 2,
            max_px=_MAX_HERO_PX,
            min_px=_MIN_HERO_PX,
        )

        return card_html(
            caption=fit_caption(self.config.label or "", ctx, box_w) if show_caption else None,
            hero=hero_block(hero),
            hero_is_html=True,
            hero_color=css_rgb(self.config.color) if self.config.color else None,
            ctx=ctx,
        )

    def _get_text(self, state: WidgetState) -> str:
        """Get the text to display.

        If entity_id is set (from options or widget config), returns the entity state.
        Otherwise returns the configured text.
        """
        if state.entity:
            return state.entity.state
        if self.dynamic_entity_id:
            entity = state.get_entity(self.dynamic_entity_id)
            if entity:
                return entity.state
        return self.text

    def get_entities(self) -> list[str]:
        """Return entity IDs this widget depends on."""
        entities = []
        if self.config.entity_id:
            entities.append(self.config.entity_id)
        if self.dynamic_entity_id and self.dynamic_entity_id != self.config.entity_id:
            entities.append(self.dynamic_entity_id)
        return entities
