"""Base layout class.

Layouts compute slot rectangles (pure geometry); rendering happens by
rasterizing each widget's HTML fragment with the Blitz engine at the
slot size and alpha-compositing the passes:

1. fullscreen theme backdrop
2. per-slot widget cells (transparent background)
3. optional fullscreen theme overlay (scanlines, vignettes)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..const import DISPLAY_HEIGHT, DISPLAY_WIDTH
from ..htmldoc import (
    HAS_BLITZ,
    HAS_FRAMES,
    HAS_LAYERS,
    CellContext,
    build_cell_document,
    build_fullscreen_document,
    composite_premultiplied,
    render_document,
    render_document_frames,
    render_layers_image,
)
from ..widgets.state import WidgetState
from ..widgets.theme import DEFAULT_THEME, Theme

if TYPE_CHECKING:
    from PIL import Image, ImageDraw

    from ..renderer import Renderer
    from ..widgets.base import Widget

_LOGGER = logging.getLogger(__name__)

_ERROR_FRAGMENT = '<div class="cell"><div class="t-label">WIDGET ERROR</div></div>'

# Glow underlay for themes that opt in (neon): each cell is painted
# once blurred beneath its sharp pass, the classic phosphor-bloom look.
# Blur is in device px at scale 1 (multiplied by the render scale).
_GLOW_BLUR_PX = 3.5
_GLOW_OPACITY = 0.55


def _css_hex(color: tuple[int, int, int]) -> str:
    """RGB tuple as a #rrggbb hex string (render_layers background)."""
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


@dataclass
class Slot:
    """Represents a widget slot in a layout."""

    index: int
    rect: tuple[int, int, int, int]  # x1, y1, x2, y2
    widget: Widget | None = None


class Layout(ABC):
    """Base class for display layouts."""

    def __init__(self, padding: int | None = None, gap: int | None = None) -> None:
        """Initialize the layout.

        Args:
            padding: Padding around the edges. When ``None`` (default),
                ``self.padding`` resolves to the active theme's
                ``layout_padding`` at access time, so changing the theme
                via ``layout.theme = ...`` automatically updates spacing.
                Passing an explicit value pins it and ignores the theme.
            gap: Gap between widgets. Same semantics as ``padding``.
        """
        self._padding_override = padding
        self._gap_override = gap
        self._theme: Theme = DEFAULT_THEME
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        self.slots: list[Slot] = []
        self._calculate_slots()

    @property
    def padding(self) -> int:
        """Outer padding — explicit override or theme default."""
        return (
            self._padding_override
            if self._padding_override is not None
            else self._theme.layout_padding
        )

    @property
    def gap(self) -> int:
        """Inter-widget gap — explicit override or theme default."""
        return self._gap_override if self._gap_override is not None else self._theme.gap

    @property
    def theme(self) -> Theme:
        """Active theme."""
        return self._theme

    @theme.setter
    def theme(self, value: Theme) -> None:
        """Set the active theme and rebuild slots so theme-driven padding/gap
        actually take effect (e.g. retro/soft/candy ship larger padding=8)."""
        self._theme = value
        # Recompute slot rectangles with the new theme's padding/gap, but
        # preserve any widgets already placed in those slots.
        existing_widgets = [slot.widget for slot in self.slots]
        self._calculate_slots()
        for i, widget in enumerate(existing_widgets):
            if widget is not None and i < len(self.slots):
                self.slots[i].widget = widget

    @abstractmethod
    def _calculate_slots(self) -> None:
        """Calculate the slot rectangles. Override in subclasses."""

    def _available_space(self) -> tuple[int, int]:
        """Calculate available width and height after padding.

        Returns:
            Tuple of (available_width, available_height)
        """
        return (
            self.width - 2 * self.padding,
            self.height - 2 * self.padding,
        )

    def _grid_cell_size(self, rows: int, cols: int) -> tuple[int, int]:
        """Calculate cell size for a grid layout.

        Args:
            rows: Number of rows
            cols: Number of columns

        Returns:
            Tuple of (cell_width, cell_height)
        """
        aw, ah = self._available_space()
        return (
            (aw - (cols - 1) * self.gap) // cols,
            (ah - (rows - 1) * self.gap) // rows,
        )

    def _split_dimension(self, total: int, ratio: float) -> tuple[int, int]:
        """Split a dimension by ratio, accounting for gap.

        Args:
            total: Total available dimension (excluding gap)
            ratio: Ratio for first section (0.0-1.0)

        Returns:
            Tuple of (first_size, second_size)
        """
        content = total - self.gap
        first = int(content * ratio)
        second = content - first
        return first, second

    def get_slot_count(self) -> int:
        """Return the number of widget slots."""
        return len(self.slots)

    def get_slot(self, index: int) -> Slot | None:
        """Get a slot by index."""
        if 0 <= index < len(self.slots):
            return self.slots[index]
        return None

    def set_widget(self, index: int, widget: Widget) -> None:
        """Set a widget in a slot.

        Args:
            index: Slot index
            widget: Widget to place
        """
        if 0 <= index < len(self.slots):
            self.slots[index].widget = widget

    def _cell_documents(
        self, widget_states: dict[int, WidgetState]
    ) -> list[tuple[Slot, str, bool]]:
        """(slot, cell document, animated) for every placed widget."""
        theme = self.theme
        cells: list[tuple[Slot, str, bool]] = []
        for slot in self.slots:
            widget = slot.widget
            if widget is None:
                continue
            x1, y1, x2, y2 = slot.rect
            ctx = CellContext(width=x2 - x1, height=y2 - y1, slot_index=slot.index, theme=theme)
            state = widget_states.get(slot.index, WidgetState())
            try:
                fragment = widget.render_html(ctx, state)
            except Exception:
                _LOGGER.exception("Widget %s failed to render", type(widget).__name__)
                fragment = _ERROR_FRAGMENT
            cells.append((slot, build_cell_document(fragment, theme), widget.is_animated()))
        return cells

    def _layer_specs(
        self,
        cells: list[tuple[Slot, str, bool]],
        scale: float,
        *,
        with_overlay: bool = True,
    ) -> list[dict]:
        """Layer list for ``render_layers``: backdrop, cells, overlay.

        Cell layers are clipped to their rects by the engine — the same
        containment the per-cell rasters used to provide. Glow themes
        paint each cell once blurred beneath its sharp pass.
        ``with_overlay=False`` leaves the theme overlay off (the animated
        path composites it above per-frame cells instead).
        """
        theme = self.theme
        backdrop_css = theme.backdrop_css or "body { background: var(--bg); }"
        layers: list[dict] = [
            {
                "html": build_fullscreen_document(theme, backdrop_css),
                "width": self.width,
                "height": self.height,
                "scale": scale,
            }
        ]
        for slot, document, animated in cells:
            x1, y1, x2, y2 = slot.rect
            # "_animated" marks layers render_animation must clock per
            # frame; it is stripped before reaching the engine.
            spec = {
                "html": document,
                "width": x2 - x1,
                "height": y2 - y1,
                "x": x1 * scale,
                "y": y1 * scale,
                "scale": scale,
                "_animated": animated,
            }
            if theme.glow_effect:
                layers.append({**spec, "blur": _GLOW_BLUR_PX * scale, "opacity": _GLOW_OPACITY})
            layers.append(spec)
        if with_overlay and theme.overlay_css:
            layers.append(
                {
                    "html": build_fullscreen_document(theme, theme.overlay_css),
                    "width": self.width,
                    "height": self.height,
                    "scale": scale,
                }
            )
        return layers

    def render(
        self,
        renderer: Renderer,
        draw: ImageDraw.ImageDraw,
        widget_states: dict[int, WidgetState] | None = None,
    ) -> None:
        """Render the screen through the Blitz pipeline.

        On blitz-py >= 0.4.0 the whole screen — theme backdrop, widget
        cells at their slot rects, optional overlay — is composited
        engine-side in one ``render_layers`` call. Older engines fall
        back to per-document rendering with Pillow compositing.

        Args:
            renderer: Renderer instance (canvas scale + encoding)
            draw: ImageDraw whose underlying image is the target canvas
            widget_states: Dict mapping slot index to WidgetState
        """
        canvas = draw._image  # noqa: SLF001
        scale = renderer.scale
        theme = self.theme

        if not HAS_BLITZ:
            self._render_missing_blitz(canvas, draw)
            return

        if widget_states is None:
            widget_states = {}
        cells = self._cell_documents(widget_states)

        if HAS_LAYERS:
            layers = [
                {k: v for k, v in spec.items() if not k.startswith("_")}
                for spec in self._layer_specs(cells, scale)
            ]
            surface = render_layers_image(
                layers,
                self.width * scale,
                self.height * scale,
                background=_css_hex(theme.background),
            )
            if surface is not None:
                canvas.paste(surface, (0, 0))
                return
            # Engine-side compositing failed — fall through to legacy.

        self._render_legacy(canvas, cells, scale)

    def _render_legacy(
        self, canvas: Image.Image, cells: list[tuple[Slot, str, bool]], scale: int
    ) -> None:
        """Per-document rendering + Pillow compositing (blitz-py < 0.4)."""
        theme = self.theme
        backdrop_css = theme.backdrop_css or "body { background: var(--bg); }"
        backdrop = render_document(
            build_fullscreen_document(theme, backdrop_css), self.width, self.height, scale=scale
        )
        if backdrop is not None:
            canvas.paste(backdrop.convert("RGB"), (0, 0))

        for slot, document, _animated in cells:
            x1, y1, x2, y2 = slot.rect
            cell = render_document(document, x2 - x1, y2 - y1, scale=scale)
            if cell is not None:
                # Blitz returns premultiplied alpha — a plain
                # paste-with-mask would apply alpha twice.
                composite_premultiplied(canvas, cell, (x1 * scale, y1 * scale))

        if theme.overlay_css:
            overlay = render_document(
                build_fullscreen_document(theme, theme.overlay_css),
                self.width,
                self.height,
                scale=scale,
            )
            if overlay is not None:
                composite_premultiplied(canvas, overlay, (0, 0))

    def has_animated_widgets(self) -> bool:
        """True when any placed widget opted into animation."""
        return any(slot.widget is not None and slot.widget.is_animated() for slot in self.slots)

    def render_animation(
        self,
        renderer: Renderer,
        widget_states: dict[int, WidgetState] | None = None,
        times: list[float] | None = None,
    ) -> list[Image.Image] | None:
        """Render the screen at several animation timestamps.

        Static passes (backdrop, non-animated cells) render once and are
        shared across frames; each animated cell renders all its frames
        in a single ``render_frames`` call. Returns one supersampled RGB
        canvas per timestamp (encode with :meth:`Renderer.to_gif`), or
        None when frame rendering is unavailable — callers fall back to
        the still pipeline.
        """
        if not (HAS_BLITZ and HAS_FRAMES) or not times:
            return None
        if widget_states is None:
            widget_states = {}
        scale = renderer.scale
        theme = self.theme
        cells = self._cell_documents(widget_states)

        # blitz-py 0.4.0's render_layers documents a per-layer ``time``
        # but does not apply it (animations render at t=0) — so the
        # static base goes through one layered call and the animated
        # cells still come from render_frames, composited per frame.
        # Fold the per-frame compositing back into render_layers once
        # the clock works upstream.
        if HAS_LAYERS:
            static_cells = [c for c in cells if not c[2]]
            base = render_layers_image(
                [
                    {k: v for k, v in spec.items() if not k.startswith("_")}
                    for spec in self._layer_specs(static_cells, scale, with_overlay=False)
                ],
                self.width * scale,
                self.height * scale,
                background=_css_hex(theme.background),
            )
            if base is not None:
                animated: list[tuple[tuple[int, int], list[Image.Image]]] = []
                for slot, document, _ in (c for c in cells if c[2]):
                    x1, y1, x2, y2 = slot.rect
                    frames = render_document_frames(document, x2 - x1, y2 - y1, times, scale=scale)
                    if frames:
                        animated.append(((x1 * scale, y1 * scale), frames))
                        continue
                    still = render_document(document, x2 - x1, y2 - y1, scale=scale)
                    if still is not None:
                        composite_premultiplied(base, still, (x1 * scale, y1 * scale))

                overlay = None
                if theme.overlay_css:
                    overlay = render_document(
                        build_fullscreen_document(theme, theme.overlay_css),
                        self.width,
                        self.height,
                        scale=scale,
                    )

                canvases: list[Image.Image] = []
                for i in range(len(times)):
                    frame = base.copy()
                    for pos, frames in animated:
                        composite_premultiplied(frame, frames[min(i, len(frames) - 1)], pos)
                    if overlay is not None:
                        composite_premultiplied(frame, overlay, (0, 0))
                    canvases.append(frame)
                return canvases
            # Engine-side compositing failed — fall through to legacy.

        return self._render_animation_legacy(renderer, cells, times, scale)

    def _render_animation_legacy(
        self,
        renderer: Renderer,
        cells: list[tuple[Slot, str, bool]],
        times: list[float],
        scale: int,
    ) -> list[Image.Image] | None:
        """Frame rendering with Pillow compositing (blitz-py < 0.4)."""
        theme = self.theme

        # Static base: backdrop + every non-animated cell, rendered once.
        base, _ = renderer.create_canvas(background=theme.background)
        animated: list[tuple[tuple[int, int], list[Image.Image]]] = []

        backdrop_css = theme.backdrop_css or "body { background: var(--bg); }"
        backdrop = render_document(
            build_fullscreen_document(theme, backdrop_css), self.width, self.height, scale=scale
        )
        if backdrop is not None:
            base.paste(backdrop.convert("RGB"), (0, 0))

        for slot, document, is_animated in cells:
            x1, y1, x2, y2 = slot.rect
            cell_w, cell_h = x2 - x1, y2 - y1
            pos = (x1 * scale, y1 * scale)
            if is_animated:
                frames = render_document_frames(document, cell_w, cell_h, times, scale=scale)
                if frames:
                    animated.append((pos, frames))
                    continue
                # Frame render failed — fall through to a still cell.
            cell = render_document(document, cell_w, cell_h, scale=scale)
            if cell is not None:
                composite_premultiplied(base, cell, pos)

        overlay = None
        if theme.overlay_css:
            overlay = render_document(
                build_fullscreen_document(theme, theme.overlay_css),
                self.width,
                self.height,
                scale=scale,
            )

        canvases: list[Image.Image] = []
        for i in range(len(times)):
            frame = base.copy()
            for pos, frames in animated:
                cell_frame = frames[min(i, len(frames) - 1)]
                composite_premultiplied(frame, cell_frame, pos)
            if overlay is not None:
                composite_premultiplied(frame, overlay, (0, 0))
            canvases.append(frame)
        return canvases

    def _render_missing_blitz(self, canvas: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        """Paint an instructive error screen when blitz-py is missing."""
        draw.rectangle((0, 0, canvas.width, canvas.height), fill=(0, 0, 0))
        message = "blitz-py required\npip install blitz-py"
        draw.text(
            (canvas.width // 2, canvas.height // 2),
            message,
            fill=(255, 159, 10),
            anchor="mm",
            align="center",
        )

    def get_all_entities(self) -> list[str]:
        """Get all entity IDs from all widgets."""
        entities = []
        for slot in self.slots:
            if slot.widget is not None:
                entities.extend(slot.widget.get_entities())
        return entities
