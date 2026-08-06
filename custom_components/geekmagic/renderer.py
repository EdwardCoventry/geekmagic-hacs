"""Canvas and image encoding for the Blitz rendering pipeline.

All drawing happens in the Blitz engine (see ``htmldoc.py`` and
``layouts/base.py``); this module only provides the composite canvas
and JPEG/PNG encoding for the device upload.

The canvas is supersampled (``SUPERSAMPLE_SCALE``); Blitz renders each
pass at the matching device-pixel ratio, so the final downscale keeps
edges crisp.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from .const import (
    COLOR_BLACK,
    DEFAULT_JPEG_QUALITY,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    SUPERSAMPLE_SCALE,
)


class Renderer:
    """Provides the composite canvas and encodes the final image."""

    def __init__(self) -> None:
        """Initialize the renderer."""
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        self._scale = SUPERSAMPLE_SCALE
        self._scaled_width = self.width * self._scale
        self._scaled_height = self.height * self._scale

    @property
    def scale(self) -> int:
        """Return the supersampling scale factor."""
        return self._scale

    def create_canvas(
        self, background: tuple[int, int, int] = COLOR_BLACK
    ) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        """Create a new image canvas at supersampled resolution.

        Args:
            background: RGB background color tuple

        Returns:
            Tuple of (Image, ImageDraw)
        """
        img = Image.new("RGB", (self._scaled_width, self._scaled_height), background)
        draw = ImageDraw.Draw(img)
        return img, draw

    def _downscale(self, img: Image.Image) -> Image.Image:
        """Downscale supersampled image to final resolution with anti-aliasing."""
        return img.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def finalize(self, img: Image.Image) -> Image.Image:
        """Finalize rendering by downscaling supersampled image.

        Args:
            img: PIL Image at supersampled resolution

        Returns:
            Final anti-aliased image at display resolution
        """
        return self._downscale(img)

    def to_jpeg(
        self,
        img: Image.Image,
        quality: int = DEFAULT_JPEG_QUALITY,
        max_size: int | None = None,
        rotation: int = 0,
    ) -> bytes:
        """Convert image to JPEG bytes with optional size cap.

        Args:
            img: PIL Image
            quality: JPEG quality (0-100)
            max_size: Maximum size in bytes (reduces quality if exceeded)
            rotation: Rotation in degrees (0, 90, 180, 270)

        Returns:
            JPEG image bytes
        """
        from .const import MAX_IMAGE_SIZE

        if max_size is None:
            max_size = MAX_IMAGE_SIZE

        # Finalize (downscale) before export
        final_img = self.finalize(img)

        # Apply rotation if specified
        if rotation:
            final_img = final_img.rotate(-rotation, expand=False)

        # Try at requested quality first
        buffer = BytesIO()
        final_img.save(buffer, format="JPEG", quality=quality)
        result = buffer.getvalue()

        # Reduce quality if size exceeds max
        current_quality = quality
        while len(result) > max_size and current_quality > 20:
            current_quality -= 10
            buffer = BytesIO()
            final_img.save(buffer, format="JPEG", quality=current_quality)
            result = buffer.getvalue()

        return result

    def to_png(self, img: Image.Image, rotation: int = 0) -> bytes:
        """Convert image to PNG bytes.

        Args:
            img: PIL Image
            rotation: Rotation in degrees (0, 90, 180, 270)

        Returns:
            PNG image bytes
        """
        # Finalize (downscale) before export
        final_img = self.finalize(img)

        # Apply rotation if specified
        if rotation:
            final_img = final_img.rotate(-rotation, expand=False)

        buffer = BytesIO()
        final_img.save(buffer, format="PNG")
        return buffer.getvalue()
