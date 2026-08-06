"""Icon widget for GeekMagic displays."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ..htmldoc import css_rgb, mdi_span
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


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

        # "huge" fills the cell; "regular" is a modest fixed-feel glyph
        # (legacy behaviour capped it around 32px).
        size = "76vmin" if self.size_mode == "huge" else "clamp(16px, 22vmin, 34px)"

        icon_html = mdi_span(self.icon, "icon", f"color: {color}; font-size: {size}")
        if not icon_html:
            # Unknown icon name — fall back to the help glyph.
            icon_html = mdi_span("help", "icon", f"color: {color}; font-size: {size}")

        panel_style = (
            ' style="background: var(--surface); border-radius: var(--radius)"'
            if self.show_panel
            else ""
        )
        return f'<div class="cell"{panel_style}>{icon_html}</div>'
