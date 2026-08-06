"""HTML widget rendered with the Blitz engine via blitz-py.

Renders user-authored HTML/CSS (with Jinja templating over entity state)
to pixels using `blitz-py <https://github.com/adrienbrault/blitz-py>`_
— Stylo (CSS) + Taffy (layout) + Parley (text) + Vello (raster), no
browser required. A 240x240 cell renders in ~20ms, and the whole
pipeline already runs in the coordinator's executor thread, so the
blocking call is safe here.

blitz-py is an optional dependency: when it isn't importable the widget
degrades to an informative placeholder instead of failing the render.

The active theme is exposed to the HTML as CSS custom properties
(``--bg``, ``--text-primary``, ``--primary``, ``--success``, ...) so
user markup can stay theme-consistent without hardcoding colours.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from jinja2.sandbox import SandboxedEnvironment
from PIL import Image

from .base import Widget, WidgetConfig
from .components import THEME_TEXT_SECONDARY, Column, Component, Icon, Text

if TYPE_CHECKING:
    from ..render_context import RenderContext
    from .state import WidgetState

# Native module without type stubs; typed Any so ty doesn't require it.
blitz_py: Any
try:
    from importlib import import_module

    blitz_py = import_module("blitz_py")
    HAS_BLITZ = True
except ImportError:  # pragma: no cover - depends on environment
    blitz_py = None
    HAS_BLITZ = False

_LOGGER = logging.getLogger(__name__)

# Entity references inside the Jinja template, e.g. states('sensor.temp')
# or state_attr("climate.living", "current_temperature"). Used to declare
# entity dependencies so the coordinator pre-fetches them into WidgetState.
_ENTITY_REF_RE = re.compile(r"""\b(?:states|state_attr)\(\s*['"]([^'"]+)['"]""")


def _css_rgb(color: tuple[int, int, int]) -> str:
    """Format an RGB tuple as a CSS color."""
    return f"rgb({color[0]}, {color[1]}, {color[2]})"


def _theme_css_variables(ctx: RenderContext) -> str:
    """Build a :root CSS block exposing the active theme as variables."""
    theme = ctx.theme
    variables = {
        "--bg": theme.background,
        "--surface": theme.surface,
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
    lines = "\n".join(f"  {name}: {_css_rgb(value)};" for name, value in variables.items())
    return f":root {{\n{lines}\n}}"


# Fluid kit: opinionated utility classes injected into every document.
#
# Each cell is its own CSS viewport, so viewport units (vmin/vw/vh) and
# media queries respond to the CELL size, not the display size. That
# makes one template adapt from a 76px 3x3 cell up to 240px fullscreen:
#
# - ``.cell``      flex-column scaffold filling the cell, space-evenly
#                  (the watchOS three-band default); add ``.row`` to go
#                  horizontal
# - ``.t-hero``    primary value — scales with cell size via clamp()
# - ``.t-value``   secondary emphasized value
# - ``.t-unit``    unit suffix next to a hero
# - ``.t-label``   caps caption / label
# - ``.hide-short``  hidden when the cell is under 100px tall
# - ``.hide-narrow`` hidden when the cell is under 100px wide
# - ``.hide-small``  hidden when either dimension is under 130px
#
# Breakpoints follow the real cell sizes: 3x3 grid ~76px, 2x2 ~118px,
# halves ~118x240, fullscreen 240px.
_FLUID_KIT_CSS = """
.cell { height: 100%; display: flex; flex-direction: column; align-items: center;
        justify-content: space-evenly; text-align: center; }
.cell.row { flex-direction: row; }
.t-hero { font-size: clamp(18px, min(46vmin, 30vw), 120px); font-weight: 700;
          line-height: 1; letter-spacing: -0.03em; }
.t-value { font-size: clamp(14px, min(26vmin, 20vw), 64px); font-weight: 700;
           line-height: 1; }
.t-unit { font-size: clamp(12px, min(18vmin, 12vw), 40px); font-weight: 600;
          line-height: 1; color: var(--text-secondary); }
.t-label { font-size: clamp(10px, min(11vmin, 8vw), 17px); font-weight: 600;
           line-height: 1; letter-spacing: 0.08em; color: var(--text-tertiary); }
@media (max-height: 99px) { .hide-short { display: none; } }
@media (max-width: 99px) { .hide-narrow { display: none; } }
@media (max-height: 129px), (max-width: 129px) { .hide-small { display: none; } }
"""


def _wrap_document(user_html: str, ctx: RenderContext) -> str:
    """Wrap user HTML with theme variables, base styles, and the fluid kit."""
    return f"""<style>
{_theme_css_variables(ctx)}
html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; }}
body {{
  background: var(--bg);
  color: var(--text-primary);
  font-family: sans-serif;
}}
{_FLUID_KIT_CSS}
</style>
<body>{user_html}</body>"""


def _build_template_context(state: WidgetState) -> dict[str, Any]:
    """Build the Jinja context exposed to the user's HTML template."""

    def states(entity_id: str) -> str:
        entity = state.get_entity(entity_id)
        return entity.state if entity else "unknown"

    def state_attr(entity_id: str, attribute: str) -> Any:
        entity = state.get_entity(entity_id)
        return entity.get(attribute) if entity else None

    def is_state(entity_id: str, value: str) -> bool:
        return states(entity_id) == value

    entity = state.entity
    return {
        "entity": entity,
        "state": entity.state if entity else "",
        "name": entity.friendly_name if entity else "",
        "unit": entity.unit if entity else "",
        "attributes": entity.attributes if entity else {},
        "now": state.now,
        "states": states,
        "state_attr": state_attr,
        "is_state": is_state,
    }


def _render_template(source: str, state: WidgetState) -> str:
    """Render the user's Jinja template against widget state.

    Uses a sandboxed environment: templates come from the user's own HA
    config, but sandboxing is cheap insurance against accidental access
    to Python internals.
    """
    env = SandboxedEnvironment(autoescape=False)
    return env.from_string(source).render(**_build_template_context(state))


@dataclass
class BlitzHtml(Component):
    """Component that rasterizes an HTML document with blitz-py.

    The blitz call happens in ``render()`` where the final cell size is
    known, so the document is always rasterized at exactly the pixels it
    will occupy — no scaling artifacts.
    """

    html: str
    error_text: str | None = field(default=None)

    def measure(self, ctx: RenderContext, max_width: int, max_height: int) -> tuple[int, int]:
        return (max_width, max_height)

    def render(self, ctx: RenderContext, x: int, y: int, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return
        # Render at the canvas supersampling factor so the pasted bitmap
        # maps 1:1 onto the scaled canvas instead of being upscaled.
        scale = float(getattr(getattr(ctx, "_renderer", None), "scale", 1) or 1)
        bg = ctx.theme.background
        try:
            png = blitz_py.render_png(
                self.html,
                width=width,
                height=height,
                scale=scale,
                color_scheme="dark",
                background=f"#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}",
            )
            image = Image.open(io.BytesIO(png))
        except Exception:
            _LOGGER.exception("blitz-py failed to render HTML widget")
            font = ctx.get_font("small")
            ctx.draw_text(
                "HTML render error",
                (x + width // 2, y + height // 2),
                font,
                ctx.theme.error,
                "mm",
            )
            return
        if image.mode != "RGB":
            image = image.convert("RGB")
        ctx.draw_image(image, rect=(x, y, x + width, y + height), fit_mode="stretch")


def _placeholder(message: str) -> Component:
    """Placeholder shown when blitz-py isn't installed or HTML is empty."""
    return Column(
        children=[
            Icon("code-tags", color=THEME_TEXT_SECONDARY, max_size=40),
            Text(message, font="small", color=THEME_TEXT_SECONDARY, truncate=True),
        ],
        gap=8,
        align="center",
        justify="center",
    )


class HtmlWidget(Widget):
    """Widget that renders arbitrary HTML/CSS via the Blitz engine.

    The ``html`` option is a Jinja template with access to:

    - ``state``, ``name``, ``unit``, ``attributes`` — the primary entity
    - ``states('sensor.x')``, ``state_attr('sensor.x', 'attr')``,
      ``is_state('sensor.x', 'on')`` — any entity referenced is
      pre-fetched by the coordinator automatically
    - ``now`` — timezone-aware current datetime

    Theme colours are available in CSS as ``var(--text-primary)``,
    ``var(--primary)``, ``var(--success)``, etc.
    """

    WIDGET_TYPE: ClassVar[str] = "html"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "HTML (Blitz)",
        "needs_entity": False,
        "options": [
            {
                "key": "html",
                "type": "textarea",
                "label": "HTML Template",
                "placeholder": '<div class="screen">{{ state }}{{ unit }}</div>',
            },
            {"key": "entity_id", "type": "entity", "label": "Entity (template data)"},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the HTML widget."""
        super().__init__(config)
        self.html = config.options.get("html", "")
        self.dynamic_entity_id = config.options.get("entity_id")

    def render(self, ctx: RenderContext, state: WidgetState) -> Component:
        """Render the HTML widget."""
        if not HAS_BLITZ:
            return _placeholder("Install blitz-py")
        if not self.html.strip():
            return _placeholder("No HTML configured")

        try:
            rendered = _render_template(self.html, state)
        except Exception:
            _LOGGER.exception("Invalid Jinja template in HTML widget")
            return _placeholder("Template error")

        return BlitzHtml(html=_wrap_document(rendered, ctx))

    def get_entities(self) -> list[str]:
        """Return entity IDs this widget depends on.

        Includes the configured entity plus every entity referenced via
        ``states()`` / ``state_attr()`` in the template, so the
        coordinator pre-fetches them into ``WidgetState.entities``.
        """
        entities: list[str] = []
        if self.config.entity_id:
            entities.append(self.config.entity_id)
        if self.dynamic_entity_id and self.dynamic_entity_id not in entities:
            entities.append(self.dynamic_entity_id)
        for entity_id in _ENTITY_REF_RE.findall(self.html):
            if entity_id not in entities:
                entities.append(entity_id)
        return entities
