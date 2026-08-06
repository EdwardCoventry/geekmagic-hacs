"""Icon widget for GeekMagic displays."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ..htmldoc import css_rgb, mdi_span
from ._cardfit import cell_box
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

# Material Design Icons draw their artwork in a band roughly 0.86em tall
# and up to 1em wide, optically centred in the em box — so a glyph sized
# to the box fills it without needing a nudge.
_INK_HEIGHT = 0.86
_INK_WIDTH = 1.0

# Share of the box the glyph takes. "huge" is the cell; "regular" is a
# deliberate half-cell mark — big enough to read across a room, small
# enough to leave the cell breathing.
_SIZE_SHARES = {"huge": 0.94, "regular": 0.52}
_MIN_PX = 14.0


class IconWidget(Widget):
    """Widget that displays a static icon."""

    WIDGET_TYPE: ClassVar[str] = "icon"

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the icon widget."""
        super().__init__(config)
        self.icon = config.options.get("icon", "mdi:help")
        self.show_panel = config.options.get("show_panel", False)
        # "size" option: "regular" (default) or "huge" (fills container)
        self.size_mode = config.options.get("size", "regular")

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the icon widget."""
        # Honour an explicit per-widget colour, otherwise let the active
        # theme tint the icon via the slot's accent.
        color = css_rgb(self.config.color) if self.config.color else ctx.accent()

        # Size the glyph to the cell it actually got: the same fragment
        # spans a 74px grid slot and a 240px fullscreen cell.
        box_w, box_h = cell_box(ctx)
        fill = min(box_h / _INK_HEIGHT, box_w / _INK_WIDTH)
        share = _SIZE_SHARES.get(self.size_mode, _SIZE_SHARES["regular"])
        size_px = max(_MIN_PX, fill * share)

        style = f"color: {color}; font-size: {size_px:.1f}px"
        icon_html = mdi_span(self.icon, "icon", style)
        if not icon_html:
            # Unknown icon name — fall back to the help glyph.
            icon_html = mdi_span("help", "icon", style)

        panel_style = (
            "background: var(--surface); border-radius: var(--radius); " if self.show_panel else ""
        )
        return f'<div class="cell" style="{panel_style}justify-content: center">{icon_html}</div>'
