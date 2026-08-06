"""Camera widget for GeekMagic displays."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb, image_data_uri, mdi_span

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

from .base import Widget, WidgetConfig
from .helpers import truncate_text


class CameraWidget(Widget):
    """Widget that displays a camera snapshot."""

    WIDGET_TYPE: ClassVar[str] = "camera"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Camera",
        "needs_entity": True,
        "entity_domains": ["camera"],
        "options": [
            {
                "key": "fit",
                "type": "select",
                "label": "Fit Mode",
                "options": ["cover", "contain"],
                "default": "cover",
            },
            {"key": "show_label", "type": "boolean", "label": "Show Label", "default": False},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the camera widget."""
        super().__init__(config)
        self.show_label = config.options.get("show_label", False)
        self.fit = config.options.get("fit", "contain")

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the camera widget."""
        if state.image is None:
            label = escape(self.config.label or "No Image")
            return (
                '<div class="cell" style="justify-content: center; gap: 4vmin; '
                'color: var(--text-secondary)">'
                f"{mdi_span('camera', 'icon i-lg')}"
                f'<div class="t-label hide-short" style="color: var(--text-secondary)">'
                f"{label}</div>"
                "</div>"
            )

        image = state.image.convert("RGB") if state.image.mode != "RGB" else state.image
        uri = image_data_uri(image)
        fit = self.fit if self.fit in ("cover", "contain") else "contain"

        chip = ""
        if self.show_label:
            label = self.label_for(state.entity, fallback="Camera")
            # Blitz doesn't render text-overflow ellipsis — truncate in
            # Python. Mirror the CSS font-size clamp(9px, 9vmin, 15px);
            # caps + letter-spacing average ~0.72em per character.
            font_px = min(15.0, max(9.0, 0.09 * min(ctx.width, ctx.height)))
            max_chars = max(4, int(ctx.width * 0.72 / (font_px * 0.72)))
            label = truncate_text(label, max_chars)
            chip_color = css_rgb(self.config.color) if self.config.color else "var(--text-primary)"
            chip = (
                '<div style="position: absolute; top: 5%; left: 5%; '
                "background: rgba(0,0,0,0.65); border-radius: 999px; "
                "padding: 1.5% 4%; font-size: clamp(9px, 9vmin, 15px); "
                "font-weight: 600; letter-spacing: 0.08em; line-height: 1.3; "
                f"text-transform: uppercase; color: {chip_color}; max-width: 80%; "
                'overflow: hidden; white-space: nowrap; text-overflow: ellipsis">'
                f"{escape(label)}</div>"
            )

        # Image fills the entire cell edge-to-edge — no reserved space.
        return (
            '<div style="position: relative; width: 100%; height: 100%; overflow: hidden">'
            f'<img src="{uri}" style="width: 100%; height: 100%; '
            f'object-fit: {fit}; display: block">'
            f"{chip}"
            "</div>"
        )
