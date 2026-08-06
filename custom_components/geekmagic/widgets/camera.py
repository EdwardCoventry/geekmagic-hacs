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

# Measured average glyph advance (em per character) for UPPERCASE strings
# at ~0.10em tracking, plus a safety margin: Nunito ~0.72, DejaVu ~0.80.
# Blitz has no text-overflow, so the capsule label is fitted in Python.
_AVG_CAPS_ROUNDED = 0.75
_AVG_CAPS_WIDE = 0.83

# Shared optical margin for the label capsule — matches the media widget's
# album-art overlay so a camera and a media cell sit on the same grid.
_INSET = "clamp(5px, 5.5vmin, 14px)"


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
            return self._render_placeholder(ctx)

        image = state.image.convert("RGB") if state.image.mode != "RGB" else state.image
        uri = image_data_uri(image)
        fit = self.fit if self.fit in ("cover", "contain") else "contain"

        chip = self._label_capsule(ctx, state) if self.show_label else ""

        # Image fills the entire cell edge-to-edge — no reserved space.
        # ``border-radius: inherit`` picks up the theme's card rounding
        # (light/classic/soft) and stays square on the chromeless themes.
        return (
            '<div style="position: relative; width: 100%; height: 100%; '
            'overflow: hidden; border-radius: inherit">'
            f'<img src="{uri}" style="width: 100%; height: 100%; '
            f'object-fit: {fit}; display: block">'
            f"{chip}"
            "</div>"
        )

    def _render_placeholder(self, ctx: CellContext) -> str:
        """Offline / no-snapshot state — a quiet caption, not an alarm."""
        label = self.config.label or "No Image"
        font_px = min(15.0, max(10.0, 0.10 * min(ctx.width, ctx.height), 0.075 * ctx.width))
        avg = _AVG_CAPS_ROUNDED if getattr(ctx.theme, "rounded_font", True) else _AVG_CAPS_WIDE
        # .t-label tracks at 0.14em, a touch wider than the capsule.
        label = truncate_text(label, max(4, int(ctx.width * 0.88 / (font_px * (avg + 0.04)))))
        return (
            '<div class="cell" style="justify-content: center; gap: 3.5vmin">'
            f"{mdi_span('camera', 'icon i-md', 'color: var(--text-secondary)')}"
            '<div class="t-label hide-short" style="text-transform: uppercase">'
            f"{escape(label)}</div>"
            "</div>"
        )

    def _label_capsule(self, ctx: CellContext, state: WidgetState) -> str:
        """Small caps capsule naming the camera, top-left over the frame.

        Fixed black/white rgba by design: the capsule floats on
        photographic content, so its contrast must not follow the theme.
        A user-set widget colour still wins for the text.
        """
        vmin = min(ctx.width, ctx.height)
        font_px = min(12.0, max(8.0, 0.062 * vmin))
        inset_px = min(14.0, max(5.0, 0.055 * vmin))
        avg = _AVG_CAPS_ROUNDED if getattr(ctx.theme, "rounded_font", True) else _AVG_CAPS_WIDE
        # Subtract the two insets, the capsule's 0.72em side padding and
        # its 1px borders from the usable width before fitting glyphs.
        usable = ctx.width - 2 * inset_px - 1.44 * font_px - 2
        label = truncate_text(
            self.label_for(state.entity, fallback="Camera"),
            max(3, int(usable / (font_px * avg))),
        )
        color = css_rgb(self.config.color) if self.config.color else "rgba(255,255,255,0.95)"
        return (
            f'<div style="position: absolute; top: {_INSET}; left: {_INSET}; '
            "background: rgba(0,0,0,0.55); border: 1px solid rgba(255,255,255,0.12); "
            f"border-radius: 999px; padding: 0.3em 0.72em; font-size: {font_px:.1f}px; "
            "font-weight: 700; letter-spacing: 0.10em; line-height: 1.25; "
            f'text-transform: uppercase; color: {color}; white-space: nowrap">'
            f"{escape(label)}</div>"
        )
