"""HTML widget — user-authored HTML/CSS with Jinja templating.

The whole rendering pipeline is Blitz-based; this widget simply passes
the user's (Jinja-rendered) markup through as the cell fragment. The
pipeline wraps it with the theme's CSS variables, the fluid kit, and
theme chrome, so user templates can use ``var(--text-primary)``,
``.cell`` / ``.t-hero`` / ``.hide-short`` etc. directly.
"""

from __future__ import annotations

import logging
import re
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from jinja2.sandbox import SandboxedEnvironment

from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

_LOGGER = logging.getLogger(__name__)

# Entity references inside the Jinja template, e.g. states('sensor.temp')
# or state_attr("climate.living", "current_temperature"). Used to declare
# entity dependencies so the coordinator pre-fetches them into WidgetState.
_ENTITY_REF_RE = re.compile(r"""\b(?:states|state_attr)\(\s*['"]([^'"]+)['"]""")


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


def _placeholder(message: str) -> str:
    """Placeholder fragment for empty or broken templates."""
    return f'<div class="cell"><div class="t-label">{escape(message.upper())}</div></div>'


class HtmlWidget(Widget):
    """Widget that renders arbitrary HTML/CSS.

    The ``html`` option is a Jinja template with access to:

    - ``state``, ``name``, ``unit``, ``attributes`` — the primary entity
    - ``states('sensor.x')``, ``state_attr('sensor.x', 'attr')``,
      ``is_state('sensor.x', 'on')`` — any entity referenced is
      pre-fetched by the coordinator automatically
    - ``now`` — timezone-aware current datetime

    Theme colours are available in CSS as ``var(--text-primary)``,
    ``var(--primary)``, ``var(--success)``, etc., and the fluid kit
    classes (``.cell``, ``.t-hero``, ``.hide-short``, ...) work out of
    the box.
    """

    WIDGET_TYPE: ClassVar[str] = "html"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "HTML",
        "needs_entity": False,
        "options": [
            {
                "key": "html",
                "type": "textarea",
                "label": "HTML Template",
                "placeholder": (
                    '<div class="cell"><div class="t-hero">{{ state }}{{ unit }}</div></div>'
                ),
            },
            {"key": "entity_id", "type": "entity", "label": "Entity (template data)"},
            {
                "key": "animate",
                "type": "boolean",
                "label": "Animate (render CSS animations as GIF)",
                "default": False,
            },
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the HTML widget."""
        super().__init__(config)
        self.html = config.options.get("html", "")
        self.dynamic_entity_id = config.options.get("entity_id")
        self.animate = bool(config.options.get("animate", False))

    def is_animated(self) -> bool:
        """Animated when the user opted this widget in."""
        return self.animate

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the HTML widget fragment."""
        if not self.html.strip():
            return _placeholder("No HTML configured")

        try:
            return _render_template(self.html, state)
        except Exception:
            _LOGGER.exception("Invalid Jinja template in HTML widget")
            return _placeholder("Template error")

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
