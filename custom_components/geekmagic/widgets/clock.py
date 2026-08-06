"""Clock widget for GeekMagic displays."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb
from ._card import card_html, chip_html
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


class ClockWidget(Widget):
    """Widget that displays current time and date.

    The watchOS three-band pattern: caption (label), hero (time), chip
    strip (date). AM/PM (in 12-hour mode) is appended to the hero.
    """

    WIDGET_TYPE: ClassVar[str] = "clock"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Clock",
        "needs_entity": False,
        "options": [
            {"key": "show_date", "type": "boolean", "label": "Show Date", "default": True},
            {"key": "show_seconds", "type": "boolean", "label": "Show Seconds", "default": False},
            {
                "key": "time_format",
                "type": "select",
                "label": "Time Format",
                "options": ["24h", "12h"],
                "default": "24h",
            },
            {
                "key": "timezone",
                "type": "timezone",
                "label": "Timezone",
            },
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the clock widget."""
        super().__init__(config)
        self.show_date = config.options.get("show_date", True)
        self.show_seconds = config.options.get("show_seconds", False)
        self.time_format = config.options.get("time_format", "24h")
        self.timezone = config.options.get("timezone")

    def get_entities(self) -> list[str]:
        """Clock widget doesn't depend on entities."""
        return []

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the clock widget."""
        now = state.now or datetime.now(tz=UTC)

        if self.time_format == "12h":
            fmt = "%I:%M:%S %p" if self.show_seconds else "%I:%M %p"
        else:
            fmt = "%H:%M:%S" if self.show_seconds else "%H:%M"
        time_str = now.strftime(fmt)
        date_str = now.strftime("%a, %b %d") if self.show_date else None

        return card_html(
            caption=self.config.label,
            hero=time_str,
            hero_color=css_rgb(self.config.color) if self.config.color else None,
            chips=[chip_html(date_str)] if date_str else None,
        )
