"""HTML document assembly for the Blitz rendering pipeline.

The display is rendered in passes, all through the Blitz engine
(via the ``blitz-py`` package):

1. **Backdrop** — one fullscreen document carrying the theme's
   background treatment (solid, gradient, texture).
2. **Cells** — each widget renders an HTML fragment which is wrapped
   with the theme's CSS and rasterized *at the cell size* with a
   transparent background, then alpha-composited onto the backdrop.
   Because every cell is its own CSS viewport, viewport units and media
   queries respond to the CELL — one fluid template adapts from a 76px
   3x3 cell to 240px fullscreen.
3. **Overlay** — an optional fullscreen transparent document for theme
   effects (scanlines, vignettes) composited on top.

Pillow's remaining role is compositing and JPEG/PNG encoding.
"""

from __future__ import annotations

import base64
import io
import logging
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from .icons import get_mdi_char

if TYPE_CHECKING:
    from .widgets.theme import Theme

try:
    from importlib import import_module

    blitz_py: Any = import_module("blitz_py")
    HAS_BLITZ = True
except ImportError:  # pragma: no cover - depends on environment
    blitz_py = None
    HAS_BLITZ = False

_LOGGER = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).parent / "fonts"

# Font files embedded into every Blitz render. Families resolve by the
# font's internal name: "Nunito", "DejaVu Sans", "Material Design Icons".
_FONT_FILES = (
    "Nunito-Regular.ttf",
    "Nunito-SemiBold.ttf",
    "Nunito-Bold.ttf",
    "Nunito-ExtraBold.ttf",
    "DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf",
    "materialdesignicons-webfont.ttf",
)


@lru_cache(maxsize=1)
def get_font_bytes() -> tuple[bytes, ...]:
    """Load embedded font files once."""
    fonts = []
    for name in _FONT_FILES:
        path = _FONTS_DIR / name
        try:
            fonts.append(path.read_bytes())
        except OSError:
            _LOGGER.warning("Font file missing: %s", path)
    return tuple(fonts)


def css_rgb(color: tuple[int, int, int]) -> str:
    """Format an RGB tuple as a CSS color."""
    return f"rgb({color[0]}, {color[1]}, {color[2]})"


def css_rgba(color: tuple[int, int, int], alpha: float) -> str:
    """Format an RGB tuple + alpha as a CSS color."""
    return f"rgba({color[0]}, {color[1]}, {color[2]}, {alpha})"


def theme_css_variables(theme: Theme) -> str:
    """Build a :root CSS block exposing the theme palette as variables."""
    variables = {
        "--bg": theme.background,
        "--surface": theme.surface,
        "--surface-variant": theme.surface_variant,
        "--border": theme.border,
        "--text-primary": theme.text_primary,
        "--text-secondary": theme.text_secondary,
        "--text-tertiary": theme.text_tertiary,
        "--primary": theme.primary,
        "--secondary": theme.secondary,
        "--success": theme.success,
        "--warning": theme.warning,
        "--error": theme.error,
        "--info": theme.info,
        "--muted": theme.muted,
    }
    lines = "\n".join(f"  {name}: {css_rgb(value)};" for name, value in variables.items())
    accents = "\n".join(f"  --accent-{i}: {css_rgb(c)};" for i, c in enumerate(theme.accent_colors))
    return f":root {{\n{lines}\n{accents}\n  --radius: {theme.corner_radius}px;\n}}"


# Fluid kit: opinionated utility classes available in every cell.
#
# Each cell is its own CSS viewport, so viewport units (vmin/vw/vh) and
# media queries respond to the CELL size, not the display size.
#
# - ``.cell``      flex-column scaffold filling the cell, space-evenly;
#                  add ``.row`` to go horizontal
# - ``.t-hero``    primary value — scales with cell size, capped by width
# - ``.t-value``   secondary emphasized value
# - ``.t-unit``    unit suffix next to a hero
# - ``.t-label``   caps caption / label
# - ``.icon``      Material Design Icons glyph
# - ``.hide-short``  hidden when the cell is under 100px tall
# - ``.hide-narrow`` hidden when the cell is under 100px wide
# - ``.hide-small``  hidden when either dimension is under 130px
#
# Breakpoints follow the real cell sizes: 3x3 grid ~76px, 2x2 ~118px,
# fullscreen 240px.
FLUID_KIT_CSS = """
.cell { height: 100%; display: flex; flex-direction: column; align-items: center;
        justify-content: space-evenly; text-align: center; box-sizing: border-box; }
.cell.row { flex-direction: row; }
.t-hero { font-size: clamp(18px, min(46vmin, 30vw), 120px); font-weight: 700;
          line-height: 1; letter-spacing: -0.03em; white-space: nowrap; }
.t-value { font-size: clamp(14px, min(26vmin, 20vw), 64px); font-weight: 700;
           line-height: 1; white-space: nowrap; }
.t-unit { font-size: clamp(12px, min(18vmin, 12vw), 40px); font-weight: 600;
          line-height: 1; color: var(--text-secondary); white-space: nowrap; }
.t-label { font-size: clamp(10px, min(11vmin, 8vw), 17px); font-weight: 600;
           line-height: 1; letter-spacing: 0.08em; color: var(--text-tertiary);
           white-space: nowrap; }
.icon { font-family: "Material Design Icons"; font-weight: 400; line-height: 1; }
.i-lg { font-size: clamp(20px, 34vmin, 84px); }
.i-md { font-size: clamp(14px, 20vmin, 48px); }
.i-sm { font-size: clamp(11px, 12vmin, 24px); }
@media (max-height: 99px) { .hide-short { display: none !important; } }
@media (max-width: 99px) { .hide-narrow { display: none !important; } }
@media (max-height: 129px), (max-width: 129px) { .hide-small { display: none !important; } }
"""


def build_cell_document(fragment: str, theme: Theme) -> str:
    """Wrap a widget fragment into a standalone cell document.

    The body is transparent — the theme backdrop shows through — and
    ``.root`` fills the cell so themes can paint per-cell chrome
    (cards, borders) on it via ``theme.chrome_css``.
    """
    # Deferred: _card imports helpers from this module (mdi_span), so a
    # top-level import here would be circular.
    from .widgets._card import CARD_CSS  # noqa: PLC0415

    return f"""<style>
{theme_css_variables(theme)}
html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; background: transparent; }}
body {{ color: var(--text-primary); font-family: {theme.font_stack}; }}
{FLUID_KIT_CSS}
{CARD_CSS}
.root {{ width: 100%; height: 100%; box-sizing: border-box; }}
{theme.chrome_css}
</style>
<body><div class="root">{fragment}</div></body>"""


def build_fullscreen_document(theme: Theme, body_css: str, body_html: str = "") -> str:
    """Build a fullscreen (backdrop or overlay) document."""
    return f"""<style>
{theme_css_variables(theme)}
html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; }}
{body_css}
</style>
<body>{body_html}</body>"""


def render_document(
    document: str, width: int, height: int, scale: float = 1.0
) -> Image.Image | None:
    """Rasterize an HTML document to a PIL RGBA image via Blitz.

    Returns None when blitz-py is unavailable or rendering fails.
    """
    if not HAS_BLITZ:
        return None
    try:
        w, h, data = blitz_py.render_rgba(
            document,
            width=width,
            height=height,
            scale=scale,
            color_scheme="dark",
            background="#00000000",
            fonts=list(get_font_bytes()),
        )
        return Image.frombytes("RGBA", (w, h), data)
    except Exception:
        _LOGGER.exception("Blitz render failed")
        return None


def image_data_uri(image: Image.Image) -> str:
    """Encode a PIL image as a PNG data: URI for use in <img src>."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def mdi_span(icon_name: str, classes: str = "icon i-md", style: str = "") -> str:
    """Render an MDI icon as an HTML span using the embedded MDI font.

    Accepts "mdi:thermometer", "thermometer", or legacy aliases.
    Returns an empty string for unknown icons.
    """
    char = get_mdi_char(icon_name)
    if not char:
        return ""
    style_attr = f' style="{style}"' if style else ""
    return f'<span class="{classes}"{style_attr}>&#x{ord(char):X};</span>'


# ============================================================================
# SVG helpers for gauges and charts
#
# IMPORTANT: Blitz does not resolve ``var(--x)`` inside SVG paint
# attributes — always pass concrete colors (css_rgb/css_rgba of theme
# values). The var() defaults below only apply when a caller forgets,
# and render as no paint.
# ============================================================================


def svg_sparkline(
    values: list[float],
    stroke: str = "var(--primary)",
    fill_opacity: float = 0.15,
    stroke_width: float = 3.0,
) -> str:
    """Build a responsive SVG sparkline from a series of values.

    The SVG uses a 100x100 viewBox with non-uniform scaling so it
    stretches to whatever box the layout gives it.
    """
    if len(values) < 2:
        return ""
    vmin, vmax = min(values), max(values)
    spread = (vmax - vmin) or 1.0
    n = len(values) - 1
    pts = []
    for i, v in enumerate(values):
        x = i / n * 100
        y = 92 - (v - vmin) / spread * 84  # 8% margin top/bottom
        pts.append(f"{x:.1f},{y:.1f}")
    points = " ".join(pts)
    area_points = f"0,100 {points} 100,100"
    return (
        '<svg viewBox="0 0 100 100" preserveAspectRatio="none" '
        'style="width:100%;height:100%;display:block">'
        f'<polygon points="{area_points}" fill="{stroke}" fill-opacity="{fill_opacity}"/>'
        f'<polyline points="{points}" fill="none" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" vector-effect="non-scaling-stroke" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        "</svg>"
    )


def svg_ring(
    percent: float,
    stroke: str = "var(--primary)",
    track: str = "rgba(255,255,255,0.12)",
    stroke_width: float = 11.0,
    label_html: str = "",
) -> str:
    """Build an Activity-style ring gauge as SVG (square aspect).

    ``label_html`` is centered inside the ring.
    """
    percent = max(0.0, min(100.0, percent))
    radius = 50 - stroke_width / 2
    circumference = 2 * 3.14159265 * radius
    dash = circumference * percent / 100
    svg = (
        '<svg viewBox="0 0 100 100" style="width:100%;height:100%;display:block">'
        f'<circle cx="50" cy="50" r="{radius:.2f}" fill="none" '
        f'stroke="{track}" stroke-width="{stroke_width}"/>'
        f'<circle cx="50" cy="50" r="{radius:.2f}" fill="none" '
        f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-dasharray="{dash:.2f} {circumference:.2f}" '
        'transform="rotate(-90 50 50)"/>'
        "</svg>"
    )
    if label_html:
        return (
            '<div style="position:relative;height:100%;aspect-ratio:1;margin:0 auto">'
            f"{svg}"
            '<div style="position:absolute;inset:0;display:flex;flex-direction:column;'
            'align-items:center;justify-content:center">'
            f"{label_html}</div></div>"
        )
    return svg


def svg_arc(
    percent: float,
    stroke: str = "var(--primary)",
    track: str = "rgba(255,255,255,0.12)",
    stroke_width: float = 11.0,
) -> str:
    """Build a 270-degree open arc gauge as SVG (gap at the bottom)."""
    percent = max(0.0, min(100.0, percent))
    r = 50 - stroke_width / 2
    sweep = 270.0
    start_angle = 135.0  # degrees, clockwise from 3 o'clock

    def point(angle_deg: float) -> tuple[float, float]:
        a = math.radians(angle_deg)
        return (50 + r * math.cos(a), 50 + r * math.sin(a))

    def arc_path(from_deg: float, to_deg: float) -> str:
        x1, y1 = point(from_deg)
        x2, y2 = point(to_deg)
        large = 1 if (to_deg - from_deg) > 180 else 0
        return f"M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large} 1 {x2:.2f} {y2:.2f}"

    track_path = arc_path(start_angle, start_angle + sweep)
    value_deg = sweep * percent / 100
    parts = [
        '<svg viewBox="0 0 100 100" style="width:100%;height:100%;display:block">',
        f'<path d="{track_path}" fill="none" stroke="{track}" '
        f'stroke-width="{stroke_width}" stroke-linecap="round"/>',
    ]
    if value_deg > 0.5:
        value_path = arc_path(start_angle, start_angle + value_deg)
        parts.append(
            f'<path d="{value_path}" fill="none" stroke="{stroke}" '
            f'stroke-width="{stroke_width}" stroke-linecap="round"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ============================================================================
# Cell render context
# ============================================================================


@dataclass
class CellContext:
    """Context passed to widgets when rendering their HTML fragment.

    Carries the cell geometry (so widgets *can* branch on size in
    Python), the theme, and the slot index for accent cycling. Prefer
    CSS-side fluidity (kit classes, vmin, media queries) over Python
    branching where possible.
    """

    width: int
    height: int
    slot_index: int = 0
    theme: Any = None  # Theme; Any avoids a circular import at runtime
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_compact(self) -> bool:
        """True for cells too small for secondary content (3x3 grid)."""
        return self.height < 100 or self.width < 100

    def accent(self) -> str:
        """CSS color for this slot's accent (cycles the theme palette)."""
        if self.theme is None:
            return "var(--primary)"
        return css_rgb(self.theme.get_accent_color(self.slot_index))
