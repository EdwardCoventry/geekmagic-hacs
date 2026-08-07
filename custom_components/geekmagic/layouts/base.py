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
    CellContext,
    build_cell_document,
    build_fullscreen_document,
    composite_premultiplied,
    render_document,
)
from ..widgets.state import WidgetState
from ..widgets.theme import DEFAULT_THEME, Theme

if TYPE_CHECKING:
    from PIL import Image, ImageDraw

    from ..renderer import Renderer
    from ..widgets.base import Widget

_LOGGER = logging.getLogger(__name__)

_ERROR_FRAGMENT = '<div class="cell"><div class="t-label">WIDGET ERROR</div></div>'


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

    def render(
        self,
        renderer: Renderer,
        draw: ImageDraw.ImageDraw,
        widget_states: dict[int, WidgetState] | None = None,
    ) -> None:
        """Render the screen through the Blitz pipeline.

        Composites the theme backdrop, each widget cell (rasterized at
        its slot size with transparent background), and the optional
        theme overlay onto the canvas behind ``draw``.

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

        # 1. Backdrop
        backdrop_css = theme.backdrop_css or "body { background: var(--bg); }"
        backdrop_doc = build_fullscreen_document(theme, backdrop_css)
        backdrop = render_document(backdrop_doc, self.width, self.height, scale=scale)
        if backdrop is not None:
            canvas.paste(backdrop.convert("RGB"), (0, 0))

        # 2. Widget cells
        for slot in self.slots:
            widget = slot.widget
            if widget is None:
                continue

            x1, y1, x2, y2 = slot.rect
            cell_w, cell_h = x2 - x1, y2 - y1
            ctx = CellContext(width=cell_w, height=cell_h, slot_index=slot.index, theme=theme)
            state = widget_states.get(slot.index, WidgetState())

            try:
                fragment = widget.render_html(ctx, state)
            except Exception:
                _LOGGER.exception("Widget %s failed to render", type(widget).__name__)
                fragment = _ERROR_FRAGMENT

            document = build_cell_document(fragment, theme)
            cell = render_document(document, cell_w, cell_h, scale=scale)
            if cell is not None:
                # Blitz returns premultiplied alpha — a plain
                # paste-with-mask would apply alpha twice.
                composite_premultiplied(canvas, cell, (x1 * scale, y1 * scale))

        # 3. Overlay
        if theme.overlay_css:
            overlay_doc = build_fullscreen_document(theme, theme.overlay_css)
            overlay = render_document(overlay_doc, self.width, self.height, scale=scale)
            if overlay is not None:
                composite_premultiplied(canvas, overlay, (0, 0))

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
