"""HTML card primitives — the watchOS three-band pattern as markup.

``card_html`` is the HTML successor of the old ``DataCard`` component:
caption band, hero band, supporting chip strip. Band visibility is
CSS-driven via the fluid kit (captions drop in short cells, chips drop
in small cells), so one fragment adapts to every cell size.

Widgets emit semantic classes; themes restyle them via ``chrome_css``.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from ..htmldoc import mdi_span

if TYPE_CHECKING:
    from ..htmldoc import CellContext

# Styles for card structure — part of every cell document (appended to
# the fluid kit by htmldoc so themes can override).
#
# Chips are soft pills filled with --chip-bg (a text-color-derived
# neutral, so they work on dark and light themes alike).
CARD_CSS = """
.chips { display: flex; gap: 5px; align-items: center; justify-content: center; }
.chip { display: flex; gap: 0.35em; align-items: center; line-height: 1;
        font-size: clamp(10px, 11vmin, 18px); font-weight: 600;
        color: var(--text-secondary);
        background: var(--chip-bg); border-radius: 999px;
        padding: 0.42em 0.85em; }
.card-icon { line-height: 1; }
.caption-row { display: flex; gap: 0.45em; align-items: center; justify-content: center; }
/* The display:flex rules above are appended after the fluid kit, so they
   would override its single-class hide-* media rules; re-assert hiding
   with higher specificity. */
@media (max-height: 99px) {
  .caption-row.hide-short, .chips.hide-short { display: none; }
}
@media (max-height: 129px), (max-width: 129px) {
  .chips.hide-small, .caption-row.hide-small { display: none; }
}
"""


def caption_fit(ctx: CellContext | None, text: str, *, reserve_em: float = 0.0) -> str:
    """Truncate a caps caption to the width it actually has.

    Measures with the embedded font metrics (theme-aware family,
    tracking, and case) rather than an average glyph estimate. Returns
    the text unchanged when no context is available.
    """
    if ctx is None:
        return text
    from ._cardfit import cell_box, fit_caption, label_px  # noqa: PLC0415 (cycle-free, lazy)

    avail_w = cell_box(ctx)[0] - reserve_em * label_px(ctx)
    return fit_caption(text, ctx, avail_w)


def chip_html(text: str, icon: str | None = None, color: str | None = None) -> str:
    """A small icon+text supporting metric (chip strip element)."""
    style = f' style="color: {color}"' if color else ""
    icon_html = mdi_span(icon, "icon") if icon else ""
    return f'<span class="chip"{style}>{icon_html}<span>{escape(text)}</span></span>'


def card_html(
    *,
    caption: str | None = None,
    caption_hide: str = "hide-short",
    icon: str | None = None,
    icon_color: str | None = None,
    icon_role: str = "chip",
    icon_size: float | None = None,
    hero: str = "",
    hero_color: str | None = None,
    chips: list[str] | None = None,
    chips_hide: str = "hide-small",
    extra: str = "",
    hero_is_html: bool = False,
    ctx: CellContext | None = None,
) -> str:
    """Build the three-band card fragment.

    Args:
        caption: Caps label band (auto-hidden in short cells).
        caption_hide: Which kit breakpoint sheds the caption row
            ("hide-short" by default, or "" to always keep it — a widget
            that shrinks its caption for short cells manages visibility
            itself).
        icon: MDI icon name.
        icon_color: CSS color for the icon.
        icon_role: "feature" renders the icon as its own band above the
            caption; "chip" keeps it inline beside the caption.
        icon_size: Explicit glyph size in px for a feature icon
            (overrides the kit's ``i-md`` clamp).
        hero: Primary value text.
        hero_color: CSS color for the hero (default: theme text).
        chips: Pre-rendered chip fragments (see :func:`chip_html`).
        chips_hide: Which kit breakpoint sheds the chip strip
            ("hide-small", "hide-short", or "" to always keep it).
        extra: Raw HTML appended after the chip strip (indicators).
        hero_is_html: Set True when ``hero`` is already markup.
        ctx: When provided, captions are truncated in Python with real
            font metrics (Blitz has no ellipsis and clips mid-glyph).
    """
    bands: list[str] = []

    icon_style = f"color: {icon_color}" if icon_color else ""
    if icon and icon_role == "feature":
        glyph_style = icon_style
        glyph_classes = "icon i-md"
        if icon_size is not None:
            glyph_style = f"{icon_style}; font-size: {icon_size:.0f}px".strip("; ")
            glyph_classes = "icon"
        bands.append(
            f'<div class="card-icon hide-short">{mdi_span(icon, glyph_classes, glyph_style)}</div>'
        )

    if caption:
        reserve = 1.5 if (icon and icon_role == "chip") else 0.0
        text = caption_fit(ctx, caption.upper(), reserve_em=reserve)
        if text or (icon and icon_role == "chip"):
            caption_inner = escape(text)
            if icon and icon_role == "chip":
                caption_inner = mdi_span(icon, "icon i-sm", icon_style) + caption_inner
            hide = f" {caption_hide}" if caption_hide else ""
            bands.append(f'<div class="t-label caption-row{hide}">{caption_inner}</div>')

    hero_html = hero if hero_is_html else escape(hero)
    hero_style = f' style="color: {hero_color}"' if hero_color else ""
    bands.append(f'<div class="t-hero"{hero_style}>{hero_html}</div>')

    if chips:
        hide = f" {chips_hide}" if chips_hide else ""
        bands.append(f'<div class="chips{hide}">{"".join(chips)}</div>')

    if extra:
        bands.append(extra)

    return f'<div class="cell">{"".join(bands)}</div>'
