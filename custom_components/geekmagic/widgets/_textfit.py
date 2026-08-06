"""Real font metrics for Python-side text fitting.

Blitz draws no ``text-overflow`` ellipsis and does not clip text to
``overflow: hidden``, so anything that might not fit has to be measured
and truncated before it reaches the markup. These helpers measure with
the *embedded* Nunito faces — the same files Blitz rasterizes with — so
the estimate matches what actually lands on the panel.

They also answer the inverse question ("how big can this string be and
still fit?"), which is how hero values get sized to the cell instead of
to a one-size-fits-all ``clamp()``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from .helpers import truncate_text

_FONTS_DIR = Path(__file__).parent.parent / "fonts"

# Weight name -> embedded font file. Mirrors the weights the fluid kit
# uses (.t-label/.chip 600-700, .t-hero 800).
_FACES = {
    "regular": "Nunito-Regular.ttf",
    "semibold": "Nunito-SemiBold.ttf",
    "bold": "Nunito-Bold.ttf",
    "extrabold": "Nunito-ExtraBold.ttf",
}

# Measure once at this size and scale linearly — TrueType advances are
# linear in size, so one cached face per weight covers every size.
_REF_PX = 200

# Fallback average glyph width (in em) when the font file is missing.
_FALLBACK_EM = 0.55


@lru_cache(maxsize=8)
def _face(weight: str) -> ImageFont.FreeTypeFont | None:
    """Load an embedded Nunito face at the reference size."""
    name = _FACES.get(weight, _FACES["semibold"])
    try:
        return ImageFont.truetype(str(_FONTS_DIR / name), _REF_PX)
    except OSError:  # pragma: no cover - only when fonts are missing
        return None


@lru_cache(maxsize=1024)
def _ref_width(text: str, weight: str) -> float:
    """Advance width of ``text`` at the reference size, in px."""
    face = _face(weight)
    if face is None:  # pragma: no cover - only when fonts are missing
        return len(text) * _REF_PX * _FALLBACK_EM
    return float(face.getlength(text))


def text_width(text: str, px: float, weight: str = "semibold", tracking: float = 0.0) -> float:
    """Rendered width of ``text`` at ``px``.

    ``tracking`` is CSS ``letter-spacing`` in em; it adds one gap per
    character the way browsers apply it (including a trailing gap).
    """
    if not text:
        return 0.0
    return _ref_width(text, weight) * px / _REF_PX + tracking * px * len(text)


def fit_font_size(
    text: str,
    max_width: float,
    max_px: float,
    weight: str = "extrabold",
    *,
    tracking: float = 0.0,
    min_px: float = 10.0,
) -> float:
    """Largest font size at which ``text`` still fits ``max_width``.

    Capped by ``max_px`` (the caller's height budget) and floored at
    ``min_px`` so a pathological string never collapses to nothing.
    """
    if not text:
        return max_px
    unit = text_width(text, 1.0, weight, tracking)
    px = max_width / unit if unit > 0 else max_px
    return max(min_px, min(px, max_px))


def truncate_to_width(
    text: str,
    px: float,
    max_width: float,
    weight: str = "semibold",
    *,
    tracking: float = 0.0,
    style: str = "end",
    min_chars: int = 2,
) -> str:
    """Shorten ``text`` until it fits ``max_width`` at ``px``.

    Uses :func:`~.helpers.truncate_text` so the ellipsis style stays
    consistent with the rest of the widgets.
    """
    if not text or text_width(text, px, weight, tracking) <= max_width:
        return text
    for n in range(len(text) - 1, min_chars, -1):
        candidate = truncate_text(text, n, style=style)
        if text_width(candidate, px, weight, tracking) <= max_width:
            return candidate
    return truncate_text(text, min_chars, style=style)
