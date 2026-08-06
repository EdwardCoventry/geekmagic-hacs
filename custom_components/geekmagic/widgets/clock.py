"""Clock widget for GeekMagic displays."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb
from ._card import card_html, chip_html
from ._cardfit import (
    HERO_SHARE_SOLO,
    HERO_SHARE_STACKED,
    caption_visible,
    cell_box,
    chip_band_px,
    fit_caption,
    fit_hero,
    hero_block,
    label_px,
)
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

# Digits carry more optical space than letters, so the time can take
# tighter tracking than the kit's default -0.035em without touching.
_TIME_TRACKING = -0.05

_MAX_HERO_PX = 124.0
_MIN_HERO_PX = 13.0


class ClockWidget(Widget):
    """Widget that displays current time and date.

    The watchOS three-band pattern: caption (label), hero (time), chip
    strip (date). In 12-hour mode the meridiem rides the time's baseline
    as a smaller secondary suffix — the digits are the message.
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
            fmt = "%I:%M:%S" if self.show_seconds else "%I:%M"
            meridiem = now.strftime("%p")
        else:
            fmt = "%H:%M:%S" if self.show_seconds else "%H:%M"
            meridiem = ""
        time_str = now.strftime(fmt)
        date_str = now.strftime("%a, %b %d") if self.show_date else None

        box_w, box_h = cell_box(ctx)
        bands_kept = caption_visible(ctx)
        show_caption = bool(self.config.label) and bands_kept
        # The date is the clock's supporting band, so it follows the
        # caption breakpoint rather than the chip strip's: a tall 114px
        # column has plenty of room for it.
        show_date = bool(date_str) and bands_kept

        caption_band = label_px(ctx) * 1.25 if show_caption else 0.0
        date_band = chip_band_px(ctx) if show_date else 0.0
        share = HERO_SHARE_SOLO if not (show_caption or show_date) else HERO_SHARE_STACKED

        hero = fit_hero(
            time_str,
            ctx,
            box_w,
            max(16.0, (box_h - caption_band - date_band) * share),
            suffix=meridiem,
            max_px=_MAX_HERO_PX,
            min_px=_MIN_HERO_PX,
        )

        return card_html(
            caption=fit_caption(self.config.label or "", ctx, box_w) if show_caption else None,
            hero=hero_block(
                hero.text, hero.px, suffix=meridiem, tracking=_TIME_TRACKING
            ),
            hero_is_html=True,
            hero_color=css_rgb(self.config.color) if self.config.color else None,
            extra=(
                f'<div class="chips hide-short">{chip_html(date_str or "")}</div>'
                if show_date
                else ""
            ),
            ctx=ctx,
        )
