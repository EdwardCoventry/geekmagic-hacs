"""Gauge primitives shared by the gauge and progress widget families.

Bars, rings and arcs speak one visual language:

* a **track** — the accent tinted down (Apple Activity style) when the
  theme opts in, otherwise the neutral ``--track`` derived from the text
  color so it reads correctly on light themes too;
* a **fill** in the accent itself, pill-capped at every size;
* a **hero value** whose digits carry the weight while the unit sits one
  step smaller and lighter next to them, baseline aligned.

Keeping these here means a bar in ``gauge.py`` and a bar in
``progress.py`` are literally the same object.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from ..htmldoc import css_rgba
from .helpers import truncate_text

if TYPE_CHECKING:
    from ..htmldoc import CellContext

# Opacity of the neutral (untinted) track. Mirrors the kit's --track var,
# which SVG paint attributes cannot resolve.
_NEUTRAL_TRACK_OPACITY = 0.12
# Fallback when no theme is available (contexts built without one).
_NEUTRAL_TRACK_FALLBACK = "rgba(128, 128, 128, 0.20)"

# Pill radius shared by every bar, in both directions.
PILL_RADIUS = "999px"

# Ring/arc stroke as a share of the gauge diameter (SVG user units on the
# 100x100 viewBox). ~10.5% keeps the ring bold without closing the hole.
STROKE_UNITS = 10.5


def cell_box(ctx: CellContext) -> tuple[float, float]:
    """Content box of the kit's ``.cell``, in pixels.

    ``padding: 4%`` resolves against the containing block's *width* on
    every side, so a short wide cell loses far more of its height than a
    naive ``0.92 * height`` suggests. Geometry computed in Python (round
    gauges) has to account for that or it overflows the cell.
    """
    pad = ctx.width * 0.04
    return ctx.width - 2 * pad, max(8.0, ctx.height - 2 * pad)


def label_px(ctx: CellContext) -> float:
    """Rendered size of the kit's ``.t-label`` at this cell size."""
    return max(10.0, min(0.10 * min(ctx.width, ctx.height), 0.075 * ctx.width, 15.0))


def char_em(ctx: CellContext, *, caps: bool = False) -> float:
    """Average glyph advance as a share of the font size.

    Rounded (Nunito) themes pack tighter than the DejaVu/mono themes,
    which also track wider — budgeting per glyph by family keeps both
    from spilling out of the cell. The caps figures are deliberately
    generous: a wide word ("POWER CONSUMPTION") runs ~15% over the
    average, and truncating one character early beats a clipped glyph.
    """
    rounded = getattr(ctx.theme, "rounded_font", True) if ctx.theme is not None else True
    if caps:
        return 0.78 if rounded else 0.95
    return 0.53 if rounded else 0.62


def fit_caption(
    ctx: CellContext,
    text: str,
    *,
    reserve_em: float = 0.0,
    width_px: float | None = None,
) -> str:
    """Truncate a caps caption to the width it has to live in.

    Blitz has no ``text-overflow`` and ignores ``overflow: hidden`` on
    text, so every caption is fitted here instead.
    """
    px = label_px(ctx)
    per_char = px * char_em(ctx, caps=True)
    usable = (width_px if width_px is not None else ctx.width * 0.90) - reserve_em * px
    return truncate_text(text, max(3, int(usable / per_char)))


def track_css(
    ctx: CellContext,
    rgb: tuple[int, int, int] | None = None,
    *,
    svg: bool = False,
) -> str:
    """Track color for a gauge fill.

    Themes with ``tint_track`` get the accent at low opacity (the value
    and its track read as one object). Otherwise the neutral track is
    used: ``var(--track)`` in HTML, a concrete rgba in SVG — Blitz does
    not resolve ``var()`` inside SVG paint attributes.
    """
    theme = ctx.theme
    if theme is not None and theme.tint_track:
        tint = rgb if rgb is not None else theme.get_accent_color(ctx.slot_index)
        return css_rgba(tint, theme.tint_track_opacity)
    if not svg:
        return "var(--track)"
    if theme is None:
        return _NEUTRAL_TRACK_FALLBACK
    return css_rgba(theme.text_primary, _NEUTRAL_TRACK_OPACITY)


def bar_html(
    percent: float,
    *,
    color: str,
    track: str,
    thickness: str,
    vertical: bool = False,
) -> str:
    """A pill track with a pill fill.

    ``thickness`` is any CSS length (the cross-axis size). The element is
    ``flex: none`` so a flex column never squashes it — a fixed height on
    a flex child is only a *basis*, and an overflowing cell would
    otherwise shrink the bar to a hairline.
    """
    if vertical:
        return (
            f'<div style="width: {thickness}; height: 100%; flex: none; '
            f"background: {track}; border-radius: {PILL_RADIUS}; "
            'position: relative; overflow: hidden">'
            '<div style="position: absolute; left: 0; right: 0; bottom: 0; '
            f"height: {percent:.1f}%; background: {color}; "
            f'border-radius: {PILL_RADIUS}"></div>'
            "</div>"
        )
    return (
        f'<div style="width: 100%; height: {thickness}; flex: none; '
        f'background: {track}; border-radius: {PILL_RADIUS}; overflow: hidden">'
        f'<div style="width: {percent:.1f}%; height: 100%; background: {color}; '
        f'border-radius: {PILL_RADIUS}"></div>'
        "</div>"
    )


# Width of one hero digit as a share of its font size (Nunito ExtraBold
# and DejaVu Bold both land near this) — used to size heroes so the
# digits + unit always fit the cell instead of being clipped (Blitz has
# no ellipsis and does not honour overflow: hidden on text).
_DIGIT_EM = 0.65
# A unit renders at this share of the hero size (mirrors the kit ratio
# between .t-hero and .t-unit).
_UNIT_RATIO = 0.38


def hero_metrics(digits: str, unit: str = "") -> float:
    """Effective character count of a "digits + unit" hero."""
    return len(digits) + _UNIT_RATIO * 1.1 * len(unit) + 0.12


def hero_font_css(
    digits: str,
    unit: str = "",
    *,
    cap_vw: float = 38.0,
    cap_vmin: float = 48.0,
) -> tuple[str, str]:
    """Return ``(hero, unit)`` font-size CSS for a value + unit pair.

    The kit's ``.t-hero`` caps at ``30vw`` because it must survive a
    five-character value. Gauges know their own string, so the width cap
    is derived from it — short values grow, long ones shrink, and
    nothing is ever clipped.
    """
    cap = min(cap_vw, 90.0 / (_DIGIT_EM * hero_metrics(digits, unit)))
    hero = f"clamp(16px, min({cap_vmin:.0f}vmin, {cap:.1f}vw), 124px)"
    unit_css = (
        f"clamp(11px, min({cap_vmin * _UNIT_RATIO:.0f}vmin, {cap * _UNIT_RATIO:.1f}vw), 46px)"
    )
    return hero, unit_css


def hero_font_px(digits: str, unit: str, box: float, *, fill: float = 0.94) -> float:
    """Largest hero size whose digits + unit fit inside ``box`` pixels."""
    return max(11.0, fill * box / (_DIGIT_EM * hero_metrics(digits, unit)))


def value_unit_html(
    digits: str,
    unit: str = "",
    *,
    hero_css: str | None = None,
    unit_css: str | None = None,
    color: str | None = None,
    unit_color: str | None = None,
    hero_class: str = "t-hero",
) -> str:
    """Hero value with the unit baseline-aligned beside it.

    The unit keeps its own (smaller, lighter) type so "73" reads as the
    number and "%" as an annotation — the same relationship Apple uses
    for every large metric.
    """
    if not digits and not unit:
        return ""
    hero_style = f"font-size: {hero_css};" if hero_css else ""
    if color:
        hero_style += f" color: {color};"
    hero_attr = f' style="{hero_style.strip()}"' if hero_style else ""
    hero_html = f'<span class="{hero_class}"{hero_attr}>{escape(digits)}</span>'
    if not unit:
        return hero_html
    unit_style = f"font-size: {unit_css};" if unit_css else ""
    if unit_color:
        unit_style += f" color: {unit_color};"
    unit_attr = f' style="{unit_style.strip()}"' if unit_style else ""
    unit_html = f'<span class="t-unit"{unit_attr}>{escape(unit)}</span>'
    return (
        '<div style="display: flex; align-items: baseline; justify-content: center; '
        f'gap: 0.07em">{hero_html}{unit_html}</div>'
    )
