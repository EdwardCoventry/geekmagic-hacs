"""Tests for the HTML (Blitz) widget."""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from custom_components.geekmagic.render_context import RenderContext
from custom_components.geekmagic.renderer import Renderer
from custom_components.geekmagic.widgets.base import WidgetConfig
from custom_components.geekmagic.widgets.components import Column
from custom_components.geekmagic.widgets.html import (
    HAS_BLITZ,
    BlitzHtml,
    HtmlWidget,
    _render_template,
    _wrap_document,
)
from custom_components.geekmagic.widgets.state import EntityState, WidgetState


@pytest.fixture
def renderer():
    """Create a renderer instance."""
    return Renderer()


@pytest.fixture
def render_context(renderer):
    """Create a RenderContext for widgets."""
    _, draw = renderer.create_canvas()
    return RenderContext(draw, (10, 10, 130, 130), renderer)


@pytest.fixture
def widget_state():
    """Widget state with a primary entity and one extra entity."""
    return WidgetState(
        entity=EntityState(
            entity_id="sensor.temperature",
            state="21.5",
            attributes={"friendly_name": "Living Room", "unit_of_measurement": "°C"},
        ),
        entities={
            "climate.living_room": EntityState(
                entity_id="climate.living_room", state="heat", attributes={}
            ),
        },
        now=datetime.now(tz=UTC),
    )


def make_widget(html: str, entity_id: str | None = "sensor.temperature") -> HtmlWidget:
    """Create an HtmlWidget with the given template."""
    return HtmlWidget(
        WidgetConfig(widget_type="html", slot=0, entity_id=entity_id, options={"html": html})
    )


class TestTemplateRendering:
    """Jinja template context and rendering."""

    def test_primary_entity_variables(self, widget_state):
        result = _render_template("{{ name }}: {{ state }}{{ unit }}", widget_state)
        assert result == "Living Room: 21.5°C"

    def test_states_function(self, widget_state):
        result = _render_template("{{ states('climate.living_room') }}", widget_state)
        assert result == "heat"

    def test_states_unknown_entity(self, widget_state):
        result = _render_template("{{ states('sensor.missing') }}", widget_state)
        assert result == "unknown"

    def test_state_attr_function(self, widget_state):
        result = _render_template(
            "{{ state_attr('sensor.temperature', 'unit_of_measurement') }}", widget_state
        )
        assert result == "°C"

    def test_is_state_function(self, widget_state):
        result = _render_template(
            "{% if is_state('climate.living_room', 'heat') %}ON{% endif %}", widget_state
        )
        assert result == "ON"

    def test_no_entity(self):
        state = WidgetState(now=datetime.now(tz=UTC))
        result = _render_template("[{{ state }}][{{ name }}]", state)
        assert result == "[][]"

    def test_css_braces_untouched(self, widget_state):
        css = "body { color: red; }"
        assert _render_template(css, widget_state) == css


class TestWrapDocument:
    """Theme CSS variable injection."""

    def test_injects_theme_variables(self, render_context):
        doc = _wrap_document("<div>hi</div>", render_context)
        assert "--text-primary:" in doc
        assert "--success:" in doc
        assert "--bg:" in doc
        assert "<div>hi</div>" in doc

    def test_base_styles(self, render_context):
        doc = _wrap_document("", render_context)
        assert "margin: 0" in doc
        assert "font-family: sans-serif" in doc

    def test_fluid_kit_injected(self, render_context):
        doc = _wrap_document("", render_context)
        for cls in (".cell", ".t-hero", ".t-value", ".t-unit", ".t-label"):
            assert cls in doc
        for cls in (".hide-short", ".hide-narrow", ".hide-small"):
            assert cls in doc


class TestGetEntities:
    """Entity dependency extraction from templates."""

    def test_config_entity_only(self):
        widget = make_widget("<div>static</div>")
        assert widget.get_entities() == ["sensor.temperature"]

    def test_extracts_states_references(self):
        widget = make_widget(
            "{{ states('climate.living_room') }} {{ state_attr(\"sensor.humidity\", 'value') }}"
        )
        assert widget.get_entities() == [
            "sensor.temperature",
            "climate.living_room",
            "sensor.humidity",
        ]

    def test_no_duplicates(self):
        widget = make_widget("{{ states('sensor.temperature') }}")
        assert widget.get_entities() == ["sensor.temperature"]

    def test_options_entity_id(self):
        widget = HtmlWidget(
            WidgetConfig(
                widget_type="html",
                slot=0,
                options={"html": "x", "entity_id": "sensor.other"},
            )
        )
        assert widget.get_entities() == ["sensor.other"]


class TestRenderFallbacks:
    """Component-tree fallbacks that don't require blitz-py."""

    def test_empty_html_placeholder(self, render_context, widget_state):
        widget = make_widget("")
        component = widget.render(render_context, widget_state)
        assert isinstance(component, Column)

    @pytest.mark.skipif(not HAS_BLITZ, reason="missing-blitz placeholder takes precedence")
    def test_invalid_template_placeholder(self, render_context, widget_state):
        widget = make_widget("{{ unclosed")
        component = widget.render(render_context, widget_state)
        assert isinstance(component, Column)

    def test_missing_blitz_placeholder(self, render_context, widget_state, monkeypatch):
        import custom_components.geekmagic.widgets.html as html_mod

        monkeypatch.setattr(html_mod, "HAS_BLITZ", False)
        widget = make_widget("<div>hi</div>")
        component = widget.render(render_context, widget_state)
        assert isinstance(component, Column)


@pytest.mark.skipif(not HAS_BLITZ, reason="blitz-py not installed")
class TestBlitzRender:
    """Real rasterization through blitz-py."""

    def test_returns_blitz_component(self, render_context, widget_state):
        widget = make_widget("<div>{{ state }}</div>")
        component = widget.render(render_context, widget_state)
        assert isinstance(component, BlitzHtml)
        assert "21.5" in component.html

    def test_renders_pixels(self, renderer, widget_state):
        """Rendering paints non-background pixels onto the canvas."""
        img, draw = renderer.create_canvas()
        ctx = RenderContext(draw, (0, 0, 240, 240), renderer)
        widget = make_widget(
            "<div style='color:#fff;font-size:60px;text-align:center'>{{ state }}</div>"
        )
        component = widget.render(ctx, widget_state)
        component.render(ctx, 0, 0, 240, 240)
        colors = img.getcolors(maxcolors=1_000_000)
        assert colors is not None
        assert len(colors) > 1  # more than just the background

    def test_hide_short_responds_to_cell_height(self, renderer, widget_state):
        """.hide-short content disappears in cells under 100px tall."""

        def red_pixels(cell_height: int) -> int:
            img, draw = renderer.create_canvas()
            ctx = RenderContext(draw, (0, 0, 240, cell_height), renderer)
            widget = make_widget(
                '<div class="hide-short" style="color:#f00;font-size:40px">XXXX</div>'
            )
            component = widget.render(ctx, widget_state)
            component.render(ctx, 0, 0, 240, cell_height)
            rgb = img.convert("RGB")
            return sum(
                count
                for count, (r, g, b) in rgb.getcolors(maxcolors=1_000_000)
                if r > 180 and g < 80 and b < 80
            )

        assert red_pixels(240) > 0
        assert red_pixels(80) == 0

    def test_fluid_hero_scales_with_cell(self, renderer, widget_state):
        """.t-hero text occupies more pixels in a larger cell."""

        def content_pixels(size: int) -> int:
            img, draw = renderer.create_canvas()
            ctx = RenderContext(draw, (0, 0, size, size), renderer)
            widget = make_widget('<div class="cell"><div class="t-hero">21.5</div></div>')
            component = widget.render(ctx, widget_state)
            component.render(ctx, 0, 0, size, size)
            rgb = img.convert("RGB")
            return sum(
                count
                for count, (r, g, b) in rgb.getcolors(maxcolors=1_000_000)
                if r > 100 or g > 100 or b > 100
            )

        assert content_pixels(240) > content_pixels(80) * 2

    def test_render_error_does_not_raise(self, renderer, widget_state, monkeypatch):
        """A blitz failure paints an error message instead of raising."""
        import custom_components.geekmagic.widgets.html as html_mod

        def boom(*args, **kwargs):
            raise RuntimeError("engine exploded")

        monkeypatch.setattr(html_mod.blitz_py, "render_png", boom)
        _img, draw = renderer.create_canvas()
        ctx = RenderContext(draw, (0, 0, 240, 240), renderer)
        widget = make_widget("<div>hi</div>")
        component = widget.render(ctx, widget_state)
        component.render(ctx, 0, 0, 240, 240)  # must not raise
