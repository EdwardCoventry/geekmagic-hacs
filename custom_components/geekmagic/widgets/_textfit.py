"""Real font metrics for Python-side text fitting.

Blitz draws no ``text-overflow`` ellipsis and does not clip text to
``overflow: hidden``, so anything that might not fit has to be measured
and truncated before it reaches the markup. These helpers measure with
the *embedded* faces Blitz rasterizes with, so the estimate matches what
lands on the panel.

Measurement is theme-aware, which matters more than it sounds: themes
are full stylesheets. ``retro`` and ``minimal`` render in DejaVu Sans
(markedly wider than Nunito) and ``retro`` additionally uppercases every
kit text class. Measuring Nunito mixed-case for a cell that will draw
DejaVu caps is how captions end up bleeding off the edge of a 240px
panel.

The module also answers the inverse question — "how big can this string
be and still fit?" — which is how hero values get sized to their cell
instead of to a one-size-fits-all ``clamp()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING
from unicodedata import east_asian_width

from PIL import ImageFont

from .helpers import truncate_text

if TYPE_CHECKING:
    from .theme import Theme

_FONTS_DIR = Path(__file__).parent.parent / "fonts"

# (family, weight) -> embedded font file. Weight names mirror the fluid
# kit (.t-label/.chip 600-700, .t-hero 800). DejaVu only ships two
# weights, so everything above regular collapses onto Bold.
_FACES = {
    ("nunito", "regular"): "Nunito-Regular.ttf",
    ("nunito", "semibold"): "Nunito-SemiBold.ttf",
    ("nunito", "bold"): "Nunito-Bold.ttf",
    ("nunito", "extrabold"): "Nunito-ExtraBold.ttf",
    ("dejavu", "regular"): "DejaVuSans.ttf",
    ("dejavu", "semibold"): "DejaVuSans-Bold.ttf",
    ("dejavu", "bold"): "DejaVuSans-Bold.ttf",
    ("dejavu", "extrabold"): "DejaVuSans-Bold.ttf",
}

# Measure once at this size and scale linearly — TrueType advances are
# linear in size, so one cached face per (family, weight) covers all.
_REF_PX = 200

# Fallback average glyph width (em) when a font file is missing.
_FALLBACK_EM = 0.60

# Letter-spacing assumptions for the kit's .t-label. The kit ships
# 0.14em; the Swiss/CRT themes (DejaVu and/or uppercase chrome) widen it
# to ~0.24em. Prefer ``TextMetrics.label_tracking`` (theme-aware) —
# measuring every theme at the widest override costs Nunito themes a
# caption character per ~10 (that's how "LIVING ROOM" became
# "LIVING RO…" on watchos).
LABEL_TRACKING = 0.24  # worst case, kept for callers without a theme
KIT_LABEL_TRACKING = 0.14
HERO_TRACKING = 0.0  # minimal resets the kit's -0.035em to 0

# East-Asian wide/fullwidth glyphs (CJK, Kana, Hangul) are not covered by
# the embedded faces: PIL reports the narrow .notdef box while Blitz
# falls back to a system face and draws them full-width. Reserve a full
# em for each so Japanese/Chinese/Korean titles never overflow the cell.
_FULLWIDTH_CLASSES = ("W", "F")
_FULLWIDTH_EM = 1.0


@lru_cache(maxsize=16)
def _face(family: str, weight: str) -> ImageFont.FreeTypeFont | None:
    """Load an embedded face at the reference size."""
    name = _FACES.get((family, weight)) or _FACES[("nunito", "semibold")]
    try:
        return ImageFont.truetype(str(_FONTS_DIR / name), _REF_PX)
    except OSError:  # pragma: no cover - only when fonts are missing
        return None


@lru_cache(maxsize=2048)
def _ref_width(text: str, family: str, weight: str) -> float:
    """Advance width of ``text`` at the reference size, in px."""
    face = _face(family, weight)
    if face is None:  # pragma: no cover - only when fonts are missing
        return len(text) * _REF_PX * _FALLBACK_EM
    return float(face.getlength(text))


@dataclass(frozen=True)
class TextMetrics:
    """Measures text the way the active theme will actually draw it."""

    family: str = "nunito"
    uppercase: bool = False
    # The .t-label letter-spacing this theme actually renders — use this
    # for caption budgets instead of the worst-case LABEL_TRACKING.
    label_tracking: float = KIT_LABEL_TRACKING

    def _measured(self, text: str) -> str:
        return text.upper() if self.uppercase else text

    def width(self, text: str, px: float, weight: str = "semibold", tracking: float = 0.0) -> float:
        """Rendered width of ``text`` at ``px``.

        ``tracking`` is CSS ``letter-spacing`` in em; browsers add one
        gap per character (including a trailing one), so that is what is
        modelled here. East-Asian wide glyphs reserve a full em each —
        the embedded faces don't cover them, and Blitz draws them
        full-width from a system fallback while PIL would report the
        narrow ``.notdef`` box.
        """
        if not text:
            return 0.0
        measured = self._measured(text)
        wide = sum(1 for c in measured if east_asian_width(c) in _FULLWIDTH_CLASSES)
        if wide:
            narrow = "".join(c for c in measured if east_asian_width(c) not in _FULLWIDTH_CLASSES)
            base = _ref_width(narrow, self.family, weight) * px / _REF_PX if narrow else 0.0
            base += wide * px * _FULLWIDTH_EM
        else:
            base = _ref_width(measured, self.family, weight) * px / _REF_PX
        return base + tracking * px * len(measured)

    def fit_font_size(
        self,
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
        unit = self.width(text, 1.0, weight, tracking)
        px = max_width / unit if unit > 0 else max_px
        return max(min_px, min(px, max_px))

    def truncate(
        self,
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

        Delegates the ellipsis to :func:`~.helpers.truncate_text` so the
        style stays consistent with the rest of the widgets.
        """
        if not text or self.width(text, px, weight, tracking) <= max_width:
            return text
        for n in range(len(text) - 1, min_chars, -1):
            candidate = truncate_text(text, n, style=style)
            if self.width(candidate, px, weight, tracking) <= max_width:
                return candidate
        return truncate_text(text, min_chars, style=style)


_DEFAULT_METRICS = TextMetrics()


def metrics_for(theme: Theme | None) -> TextMetrics:
    """Build a measurer matching how ``theme`` renders the KIT classes.

    ``uppercase`` reflects the theme's ``text-transform`` on the kit
    text classes (retro uppercases them all). Widgets measuring plain
    non-kit divs should neutralise it —
    ``replace(metrics_for(theme), uppercase=False)`` — or they will
    over-reserve for text that renders mixed-case.
    """
    if theme is None:
        return _DEFAULT_METRICS
    stack = (getattr(theme, "font_stack", "") or "").lower()
    family = "dejavu" if "dejavu" in stack.split(",")[0] else "nunito"
    chrome = (getattr(theme, "chrome_css", "") or "").lower()
    uppercase = "text-transform: uppercase" in chrome
    wide_labels = family == "dejavu" or uppercase
    return TextMetrics(
        family=family,
        uppercase=uppercase,
        label_tracking=LABEL_TRACKING if wide_labels else KIT_LABEL_TRACKING,
    )
