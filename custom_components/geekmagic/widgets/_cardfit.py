"""Cell geometry and hero typography for the card-family widgets.

The fluid kit sizes the hero with ``clamp()``, which cannot know how
long a value is: six characters at the kit's cap overflow a 240px panel,
and Blitz neither shrinks nor clips the overflow. So the card family
(entity, clock, text, icon) measures its own content with the embedded
font metrics (:mod:`._textfit`) and hands a fitted pixel size to the
markup.

Two shapes are shared here on purpose, so the canonical widgets stay
typographically identical:

* :func:`cell_box` — the pixel box a fragment really has, after theme
  chrome and the kit's ``.cell`` padding.
* :func:`hero_block` — the hero band: big value, optional smaller
  secondary suffix (unit, AM/PM) sitting on the same baseline.

Everything here is geometry and structure; colour stays with the theme.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING

from ._textfit import metrics_for

if TYPE_CHECKING:
    from ..htmldoc import CellContext

# Every shipped theme paints ``.root`` with up to 6px of padding plus a
# 1px border, and the kit's ``.cell`` adds 4% padding on all four sides
# (CSS resolves percentage padding against the width, vertically too).
_CHROME_INSET = 7.0
_CELL_PADDING = 0.04

# Share of the free height a hero may spend. What is left becomes the
# ``space-evenly`` gaps that give the cell its rhythm — a hero that eats
# 100% of the height reads as a cell about to burst.
HERO_SHARE_SOLO = 0.86
HERO_SHARE_STACKED = 0.78

# Kit line-heights (.t-hero is 0.95; wrapped text needs descender room).
HERO_LINE = 0.95
WRAP_LINE = 1.08

# The secondary half of a hero (unit, AM/PM) relative to the value.
SUFFIX_SCALE = 0.46
# Units that start with a symbol (°C, %) hang off the digits; word units
# (W, km/h) need a real word space.
_SUFFIX_GAP_TIGHT = 0.05
_SUFFIX_GAP_WORD = 0.16

# Widest caption tracking any theme applies (kit 0.14em, Swiss/CRT
# themes 0.24em) — measuring with the widest keeps captions inside every
# theme.
LABEL_TRACKING = 0.24

# Kit breakpoints, mirrored so Python can predict which bands survive.
HIDE_SHORT_H = 100
HIDE_SMALL = 130

# Hero weight to measure with: the kit's 800. Themes that lighten it
# only ever get narrower, so this stays on the safe side.
_HERO_WEIGHT = "extrabold"

# Wrapping only wins if it buys a meaningfully bigger value; below this
# it just costs a line break.
_WRAP_GAIN = 1.15

# A width-bound fit lands exactly on the budget, where float noise can
# read as an overflow — never truncate for less than this many pixels.
_FIT_EPS = 1.0


def cell_box(ctx: CellContext) -> tuple[float, float]:
    """Usable content box (width, height) in px inside a cell."""
    inner_w = max(12.0, ctx.width - 2 * _CHROME_INSET)
    inner_h = max(12.0, ctx.height - 2 * _CHROME_INSET)
    pad = 2 * _CELL_PADDING * inner_w
    return max(8.0, inner_w - pad), max(8.0, inner_h - pad)


def label_px(ctx: CellContext) -> float:
    """Size the kit resolves for ``.t-label`` in this cell.

    Mirrors ``clamp(10px, min(10vmin, 7.5vw), 15px)``.
    """
    return max(10.0, min(0.10 * min(ctx.width, ctx.height), 0.075 * ctx.width, 15.0))


def chip_px(ctx: CellContext) -> float:
    """Size the kit resolves for ``.chip`` — ``clamp(10px, 11vmin, 16px)``."""
    return max(10.0, min(0.11 * min(ctx.width, ctx.height), 16.0))


def chip_band_px(ctx: CellContext) -> float:
    """Outer height of a chip strip (font + the pill's 0.42em padding)."""
    return chip_px(ctx) * 1.9


def caption_visible(ctx: CellContext) -> bool:
    """True when the kit keeps ``.hide-short`` bands (caption, feature icon)."""
    return ctx.height >= HIDE_SHORT_H


def small_visible(ctx: CellContext) -> bool:
    """True when the kit keeps ``.hide-small`` bands (chip strips)."""
    return ctx.width >= HIDE_SMALL and ctx.height >= HIDE_SMALL


def fit_caption(text: str, ctx: CellContext, avail_w: float) -> str:
    """Truncate a caps caption to the width it actually has.

    ``card_html`` also truncates when given ``ctx``, but from an average
    glyph width; measuring the real caps string is what keeps long entity
    names from bleeding off the panel.
    """
    metrics = metrics_for(ctx.theme)
    return metrics.truncate(
        text.upper(),
        label_px(ctx),
        avail_w,
        "bold",
        tracking=LABEL_TRACKING,
        style="end",
        min_chars=3,
    )


def _balance(text: str) -> list[str]:
    """Split text over two lines of near-equal length (or don't)."""
    words = text.split()
    if len(words) < 2:
        return [text]
    best: tuple[int, list[str]] | None = None
    for i in range(1, len(words)):
        head, tail = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(head), len(tail))
        if best is None or score < best[0]:
            best = (score, [head, tail])
    return best[1] if best else [text]


@dataclass(frozen=True)
class HeroFit:
    """Result of fitting a hero value to its band."""

    px: float
    text: str
    wrapped: bool = False


def fit_hero(
    text: str,
    ctx: CellContext,
    avail_w: float,
    avail_h: float,
    *,
    suffix: str = "",
    allow_wrap: bool = False,
    max_px: float = 128.0,
    min_px: float = 12.0,
) -> HeroFit:
    """Largest size at which ``text`` (+ its suffix) fits its band.

    When ``allow_wrap`` is set, a multi-word value may take two lines if
    that lets the type be meaningfully bigger. Anything that still does
    not fit at ``min_px`` is truncated, because Blitz would otherwise
    draw it straight over the panel edge.
    """
    metrics = metrics_for(ctx.theme)
    if not text:
        return HeroFit(min_px, text)

    reserve = suffix_width_em(suffix, ctx)
    per_px = metrics.width(text, 1.0, _HERO_WEIGHT) + reserve
    px = min(max_px, avail_w / max(per_px, 1e-6), avail_h / HERO_LINE)

    wrapped = False
    if allow_wrap and not suffix:
        lines = _balance(text)
        if len(lines) > 1:
            widest = max(metrics.width(line, 1.0, _HERO_WEIGHT) for line in lines)
            wrapped_px = min(max_px, avail_w / widest, avail_h / (2 * WRAP_LINE))
            if wrapped_px > px * _WRAP_GAIN:
                px, wrapped = wrapped_px, True

    px = max(min_px, px)
    if wrapped:
        # The min_px floor can undo the wrap fit; fall back to one
        # truncated line rather than draw over the edge.
        wrapped = all(
            metrics.width(line, px, _HERO_WEIGHT) <= avail_w + _FIT_EPS for line in _balance(text)
        )
    if not wrapped:
        budget = avail_w - reserve * px
        if metrics.width(text, px, _HERO_WEIGHT) > budget + _FIT_EPS:
            text = metrics.truncate(text, px, budget, _HERO_WEIGHT, style="end", min_chars=2)
    return HeroFit(px, text, wrapped)


def suffix_width_em(suffix: str, ctx: CellContext) -> float:
    """Width a hero suffix adds, in hero-em (0 when there is none)."""
    if not suffix:
        return 0.0
    metrics = metrics_for(ctx.theme)
    gap = _SUFFIX_GAP_WORD if suffix[0].isalnum() else _SUFFIX_GAP_TIGHT
    return metrics.width(suffix, 1.0, "bold") * SUFFIX_SCALE + gap


def hero_block(
    text: str,
    px: float,
    *,
    suffix: str = "",
    wrapped: bool = False,
    tracking: float | None = None,
) -> str:
    """The hero band: fitted value plus an optional secondary suffix.

    Rendered as a block child of ``.t-hero``: a block child suppresses
    the parent's line-box strut, so the band is exactly as tall as the
    fitted type instead of reserving room for the kit's ``clamp()`` cap.
    The suffix is an inline ``.t-unit`` span, which puts it on the value's
    baseline — smaller and secondary, the way a unit should read.
    """
    style = f"font-size: {px:.1f}px; line-height: {WRAP_LINE if wrapped else HERO_LINE}"
    if tracking is not None:
        style += f"; letter-spacing: {tracking}em"
    if wrapped:
        style += "; white-space: normal"
    body = escape(text)
    if suffix:
        gap = _SUFFIX_GAP_WORD if suffix[0].isalnum() else _SUFFIX_GAP_TIGHT
        body += (
            f'<span class="t-unit" style="font-size: {SUFFIX_SCALE}em; '
            f'margin-left: {gap}em">{escape(suffix)}</span>'
        )
    return f'<div style="{style}">{body}</div>'
