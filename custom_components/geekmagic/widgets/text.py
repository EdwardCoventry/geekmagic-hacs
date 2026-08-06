"""Text widget for GeekMagic displays."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb
from ._card import card_html
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


class TextWidget(Widget):
    """Widget that displays static or dynamic text via the card pattern.

    Maps to ``card_html(caption=label, hero=text)`` — the watchOS
    caption-above-hero pattern. The hero auto-fits the cell, so the
    legacy ``size`` option (small/regular/large/xlarge) is no longer
    needed and is silently ignored if present in stored configs.
    Likewise the legacy ``align`` option is ignored — text is centred
    in the watchOS contract.
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
        return card_html(
            caption=self.config.label,
            hero=self._get_text(state),
            hero_color=css_rgb(self.config.color) if self.config.color else None,
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
