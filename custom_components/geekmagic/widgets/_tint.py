"""Opaque tint resolution for cell fills, pills and hairlines.

Cell documents rasterize onto transparency and the layout composites
them over the backdrop, so a translucent fill only lands at its stated
strength if every stage of that hand-off is alpha-correct. Today it is
not: ``blitz_py.render_rgba`` returns *premultiplied* RGBA, which
``htmldoc.render_document`` wraps as if it were straight alpha, so
``Image.paste``/``alpha_composite`` applies the alpha a second time.
A 16% fill lands at 2.6% — invisible on any theme whose ``chrome_css``
leaves ``.root`` transparent (watchos, minimal, retro). Themes that
paint an opaque ``.root`` (light, classic, ...) are unaffected, because
Blitz composites those internally where the maths is right.

Resolving the blend here sidesteps the whole question: the widget emits
a flat ``rgb()`` that is already the colour the translucent version was
meant to produce, so it renders identically before and after that
pipeline bug is fixed. The blend target is ``theme.background``; themes
with chrome tint ``.root`` by only a few percent, so the approximation
stays well inside a rounding error.

Alphas mirror the kit's derived neutrals (``--hairline`` is text at
10%), keeping these widgets visually in step with var()-driven ones.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..htmldoc import css_rgb

if TYPE_CHECKING:
    from .theme import Color, Theme

# Kit parity: --hairline is the text colour at 10%.
HAIRLINE_ALPHA = 0.10

_FALLBACK_BG: tuple[int, int, int] = (0, 0, 0)
_FALLBACK_INK: tuple[int, int, int] = (235, 235, 235)


def blend(color: Color, background: Color, alpha: float) -> tuple[int, int, int]:
    """``color`` at ``alpha`` over ``background``, as opaque RGB."""
    a = max(0.0, min(1.0, alpha))
    return tuple(round(c * a + b * (1.0 - a)) for c, b in zip(color, background, strict=False))  # type: ignore[return-value]


def tint_css(color: Color, theme: Theme | None, alpha: float) -> str:
    """CSS colour for ``color`` shown at ``alpha`` on the theme's canvas."""
    background = getattr(theme, "background", _FALLBACK_BG) if theme else _FALLBACK_BG
    return css_rgb(blend(color, background, alpha))


def hairline_css(theme: Theme | None, alpha: float = HAIRLINE_ALPHA) -> str:
    """CSS colour for a 1px separator — the kit's ``--hairline``, resolved."""
    ink = getattr(theme, "text_primary", _FALLBACK_INK) if theme else _FALLBACK_INK
    return tint_css(ink, theme, alpha)
