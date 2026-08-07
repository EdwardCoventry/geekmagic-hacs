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
# 100% of the height reads as a cell about to burst. The kit's 4%
# padding already guarantees the outer inset, so a lone hero can be
# generous; stacked bands need room to read as separate bands.
HERO_SHARE_SOLO = 0.92
HERO_SHARE_STACKED = 0.80

# Kit line-heights (.t-hero is 0.95; wrapped text needs descender room).
HERO_LINE = 0.95
WRAP_LINE = 1.08

# The secondary half of a hero (unit, AM/PM) relative to the value.
SUFFIX_SCALE = 0.46
# Units that start with a symbol (°C, %) hang off the digits; word units
# (W, km/h) need a real word space.
_SUFFIX_GAP_TIGHT = 0.05
_SUFFIX_GAP_WORD = 0.20

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

    A stub is worse than nothing: when truncation destroys the name's
    identity ("GARAG…" for "GARAGE WORKSHOP TEMPERATURE"), the caption
    drops entirely and the cell spends the room on the value. A caption
    survives if at least 70% of its characters — or an 8-character
    prefix — make it through.
    """
    metrics = metrics_for(ctx.theme)
    upper = text.upper()
    fitted = metrics.truncate(
        upper,
        label_px(ctx),
        avail_w,
        "bold",
        tracking=metrics.label_tracking,
        style="end",
        min_chars=3,
    )
    if fitted != upper:
        kept = len(fitted.rstrip("…"))
        if kept < 8 and kept < 0.7 * len(upper):
            return ""
    return fitted


def _balance(text: str, count: int = 2) -> list[str]:
    """Split text over ``count`` lines of near-equal length.

    Balanced beats greedy here: minimising the longest line is what lets
    the type be biggest, and it avoids the orphan word a greedy wrap
    strands on the last line.
    """
    words = text.split()
    if len(words) < 2 or count < 2:
        return [text]
    count = min(count, len(words))
    # best[k][i]: shortest possible longest-line for the first i words
    # over k lines (line length measured in characters, which tracks
    # width closely enough for balancing).
    best: list[list[float]] = [[float("inf")] * (len(words) + 1) for _ in range(count + 1)]
    split: list[list[int]] = [[0] * (len(words) + 1) for _ in range(count + 1)]
    best[0][0] = 0.0
    for k in range(1, count + 1):
        for i in range(1, len(words) + 1):
            for j in range(k - 1, i):
                line = len(" ".join(words[j:i]))
                score = max(best[k - 1][j], line)
                if score < best[k][i]:
                    best[k][i] = score
                    split[k][i] = j
    lines: list[str] = []
    i = len(words)
    for k in range(count, 0, -1):
        j = split[k][i]
        lines.append(" ".join(words[j:i]))
        i = j
    return list(reversed(lines))


@dataclass(frozen=True)
class HeroFit:
    """A fitted hero: the size, and the lines it was fitted to."""

    px: float
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        """The fitted value as one string."""
        return " ".join(self.lines)

    @property
    def wrapped(self) -> bool:
        """True when the value was laid out over several lines."""
        return len(self.lines) > 1


def fit_hero(
    text: str,
    ctx: CellContext,
    avail_w: float,
    avail_h: float,
    *,
    suffix: str = "",
    suffix_scale: float = SUFFIX_SCALE,
    tracking: float = 0.0,
    allow_wrap: bool = False,
    max_lines: int = 2,
    lines: list[str] | None = None,
    max_px: float = 128.0,
    min_px: float = 12.0,
) -> HeroFit:
    """Largest size at which ``text`` (+ its suffix) fits its band.

    ``tracking`` is the letter-spacing the markup will apply, in em —
    measuring without it throws away the width tight tracking buys back.
    ``lines`` forces a multi-line layout (a clock stacking HH over MM);
    otherwise ``allow_wrap`` lets a multi-word value take up to
    ``max_lines`` lines when that makes the type meaningfully bigger.
    Anything that still does not fit at ``min_px`` is truncated, because
    Blitz would draw the overflow straight over the panel edge.
    """
    metrics = metrics_for(ctx.theme)
    if not text:
        return HeroFit(min_px, (text,))

    def per_px(value: str) -> float:
        return metrics.width(value, 1.0, _HERO_WEIGHT, tracking)

    def fit_parts(parts: list[str], reserve_em: float = 0.0) -> float:
        widest = max(per_px(part) for part in parts) + reserve_em
        return min(
            max_px,
            avail_w / max(widest, 1e-6),
            avail_h / (len(parts) * (WRAP_LINE if len(parts) > 1 else HERO_LINE)),
        )

    reserve = suffix_width_em(suffix, ctx, scale=suffix_scale)

    if lines:
        return HeroFit(max(min_px, fit_parts(lines, reserve)), tuple(lines))

    px = fit_parts([text], reserve)
    layout = [text]
    if allow_wrap and not suffix:
        for count in range(2, max_lines + 1):
            parts = _balance(text, count)
            if len(parts) < count:
                break
            candidate = fit_parts(parts)
            if candidate > px * _WRAP_GAIN:
                px, layout = candidate, parts

    px = max(min_px, px)
    if len(layout) == 1:
        # The min_px floor can push a lone line back over the budget.
        budget = avail_w - reserve * px
        if metrics.width(text, px, _HERO_WEIGHT, tracking) > budget + _FIT_EPS:
            layout = [
                metrics.truncate(
                    text, px, budget, _HERO_WEIGHT, tracking=tracking, style="end", min_chars=2
                )
            ]
    return HeroFit(px, tuple(layout))


def suffix_width_em(suffix: str, ctx: CellContext, *, scale: float = SUFFIX_SCALE) -> float:
    """Width a hero suffix adds, in hero-em (0 when there is none)."""
    if not suffix:
        return 0.0
    metrics = metrics_for(ctx.theme)
    gap = _SUFFIX_GAP_WORD if suffix[0].isalnum() else _SUFFIX_GAP_TIGHT
    return metrics.width(suffix, 1.0, "bold") * scale + gap


def hero_block(
    fit: HeroFit | str,
    px: float | None = None,
    *,
    suffix: str = "",
    suffix_scale: float = SUFFIX_SCALE,
    tracking: float | None = None,
) -> str:
    """The hero band: fitted value plus an optional secondary suffix.

    Takes the :class:`HeroFit` (which carries the line layout), or a
    ``text, px`` pair for single-line heroes.

    Rendered as a block child of ``.t-hero``: a block child suppresses
    the parent's line-box strut, so the band is exactly as tall as the
    fitted type instead of reserving room for the kit's ``clamp()`` cap.
    Multi-line heroes get one block per line rather than an engine wrap —
    Blitz breaks lines against the flex item's own width, which ignores
    the cell's percentage padding, so leaving it to wrap puts long lines
    into the margin.

    The suffix is an inline ``.t-unit`` span on the last line, which
    keeps it on the value's baseline — smaller and secondary, the way a
    unit should read.
    """
    if isinstance(fit, HeroFit):
        lines, size = fit.lines, fit.px
    else:
        lines, size = (fit,), float(px or 0.0)

    multiline = len(lines) > 1
    style = f"font-size: {size:.1f}px; line-height: {WRAP_LINE if multiline else HERO_LINE}"
    if tracking is not None:
        style += f"; letter-spacing: {tracking}em"

    tail = ""
    if suffix:
        gap = _SUFFIX_GAP_WORD if suffix[0].isalnum() else _SUFFIX_GAP_TIGHT
        tail = (
            f'<span class="t-unit" style="font-size: {suffix_scale}em; '
            f'margin-left: {gap}em">{escape(suffix)}</span>'
        )

    body = "".join(
        f"<div>{escape(line)}{tail if i == len(lines) - 1 else ''}</div>"
        if multiline
        else f"{escape(line)}{tail}"
        for i, line in enumerate(lines)
    )
    return f'<div style="{style}">{body}</div>'
