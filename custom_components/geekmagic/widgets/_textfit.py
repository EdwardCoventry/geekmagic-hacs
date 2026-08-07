"""Real font metrics for Python-side text fitting.

Blitz draws no ``text-overflow`` ellipsis and does not clip text to
``overflow: hidden``, so anything that might not fit has to be measured
and truncated before it reaches the markup. Measurement goes through
``blitz_py.measure_text`` (>= 0.3.0) — the engine's own shaper over the
same embedded font collection it rasterizes with, one source of truth
for layout math done in Python. That includes the engine's system-font
fallback, so CJK titles measure at their real fullwidth advance.

Measurement is theme-aware, which matters more than it sounds: themes
are full stylesheets. ``retro`` and ``minimal`` render in DejaVu Sans
(markedly wider than Nunito) and ``retro`` additionally uppercases the
kit's label class. Measuring Nunito mixed-case for a cell that will
draw DejaVu caps is how captions end up bleeding off the edge of a
240px panel.

The module also answers the inverse question — "how big can this string
be and still fit?" — which is how hero values get sized to their cell
instead of to a one-size-fits-all ``clamp()``.

The true fix remains native ``text-overflow: ellipsis`` in blitz-dom,
tracked upstream in the blitz-py repo (docs/UPSTREAM.md there).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from .helpers import truncate_text

try:
    from blitz_py import measure_text as _measure_text
except ImportError:  # pragma: no cover - blitz-py is a hard requirement
    _measure_text = None

if TYPE_CHECKING:
    from .theme import Theme

# CSS family names as registered by the embedded font collection.
_FAMILY_CSS = {"nunito": "Nunito", "dejavu": "DejaVu Sans"}
# Kit weight names -> CSS numeric weights. DejaVu only embeds 400/700;
# the engine's font matching collapses the rest onto the nearest face,
# the same way the rendered document does.
_WEIGHT_NUM = {"regular": 400.0, "semibold": 600.0, "bold": 700.0, "extrabold": 800.0}

# Measure once at this size and scale linearly — glyph advances are
# linear in size, so one cached measurement per (text, family, weight)
# covers every render size.
_REF_PX = 200

# Fallback average glyph width (em) when blitz-py is unavailable (the
# integration then only ever draws the install-hint screen anyway).
_FALLBACK_EM = 0.60


@lru_cache(maxsize=1)
def _font_collection() -> tuple[bytes, ...]:
    """The embedded faces, as the engine's ``fonts=`` parameter."""
    from ..htmldoc import get_font_bytes  # noqa: PLC0415 (avoid import cycle at module load)

    return get_font_bytes()


# Letter-spacing assumptions for the kit's .t-label. The kit ships
# 0.06em (tight on purpose: tracking is horizontal space that could be
# letters on a 240px panel); the Swiss/CRT themes (DejaVu and/or
# uppercase chrome) widen it to 0.12em. Prefer
# ``TextMetrics.label_tracking`` (theme-aware) — measuring every theme
# at the widest override costs Nunito themes caption characters.
LABEL_TRACKING = 0.12  # worst case, kept for callers without a theme
KIT_LABEL_TRACKING = 0.06
HERO_TRACKING = 0.0  # minimal resets the kit's -0.035em to 0


@lru_cache(maxsize=4096)
def _ref_width(text: str, family: str, weight: str) -> float:
    """Advance width of ``text`` at the reference size, in px.

    Shaped by the engine itself (Parley over the embedded collection,
    with the same system fallback the renderer uses), so the number IS
    what lands on the panel.
    """
    if _measure_text is None:  # pragma: no cover - install-hint path only
        return len(text) * _REF_PX * _FALLBACK_EM
    width, _height = _measure_text(
        text,
        font_size=float(_REF_PX),
        font_family=_FAMILY_CSS.get(family, "Nunito"),
        font_weight=_WEIGHT_NUM.get(weight, 600.0),
        fonts=_font_collection(),
    )
    return float(width)


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
        modelled here. CJK and every other script the embedded faces
        lack are shaped through the engine's own fallback, so their
        advances are the rendered ones — no reservation hacks.
        """
        if not text:
            return 0.0
        measured = self._measured(text)
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
