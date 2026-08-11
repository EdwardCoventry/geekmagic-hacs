"""Tests for the fullscreen Homeberry dashboard widget."""

from datetime import UTC, datetime, timedelta

from custom_components.geekmagic.htmldoc import CellContext
from custom_components.geekmagic.widgets import WIDGET_CLASSES, WidgetConfig
from custom_components.geekmagic.widgets.homeberry_dashboard import HomeberryDashboardWidget
from custom_components.geekmagic.widgets.state import EntityState, WidgetState
from custom_components.geekmagic.widgets.theme import DEFAULT_THEME

NOW = datetime(2026, 8, 11, 9, 42, tzinfo=UTC)
CTX = CellContext(width=240, height=240, slot_index=0, theme=DEFAULT_THEME)
TEMP = "sensor.temp_temperature"
WEATHER = "weather.forecast_home"
SCENE = "sensor.homeberry_runtime_active_scene"
CODEX = "sensor.codex_usage_codex_weekly_remaining"


def widget() -> HomeberryDashboardWidget:
    return HomeberryDashboardWidget(
        WidgetConfig(
            widget_type="homeberry_dashboard",
            entity_id=CODEX,
            options={
                "temperature_entity_id": TEMP,
                "weather_entity_id": WEATHER,
                "scene_entity_id": SCENE,
            },
        )
    )


def state(quota: str = "68") -> WidgetState:
    return WidgetState(
        entity=EntityState(
            CODEX,
            quota,
            {"secondary_reset_at": (NOW + timedelta(days=3, hours=5)).timestamp()},
        ),
        entities={
            TEMP: EntityState(TEMP, "25.6", {"unit_of_measurement": "°C"}),
            WEATHER: EntityState(WEATHER, "partlycloudy", {"temperature": 20}),
            SCENE: EntityState(SCENE, "Movie", {"active_scene_id": "movie"}),
        },
        now=NOW,
    )


def test_dashboard_resolves_all_homeberry_glance_values():
    snapshot = widget().snapshot(state())

    assert snapshot.time_text == "09:42"
    assert snapshot.date_text == "TUE 11 AUG"
    assert snapshot.temperature_text == "26°"
    assert snapshot.weather_condition == "partlycloudy"
    assert snapshot.scene_text == "MOVIE"
    assert snapshot.quota_remaining == 68
    assert snapshot.reset_text == "3d 5h"


def test_dashboard_declares_all_entity_dependencies():
    assert widget().get_entities() == [CODEX, TEMP, WEATHER, SCENE]


def test_dashboard_renders_scene_weather_and_quota():
    html = widget().render_html(CTX, state())

    assert "09:42" in html
    assert "26°" in html
    assert "PARTLY CLOUDY" not in html
    assert "hbd-weather-art" in html
    assert "MOVIE" in html
    assert "68%" in html
    assert 'class="hbd-refresh"' in html
    assert "3d 5h" in html
    assert html.index("68%") < html.index("3d 5h") < html.index('class="hbd-bar"')
    assert 'class="hbd-codex-top"' in html
    assert ".hbd-home-icon" in html and "color:#C7CBD1" in html
    assert "border-bottom" not in html and "border-left" not in html
    assert "hbd-full-b" not in html.split("</style>", 1)[1]


def test_full_quota_alternates_dashboard_and_reset_faces():
    dashboard = widget()
    html = dashboard.render_html(CTX, state("100"))

    assert "hbd-dashboard" in html
    assert "CODEX" in html and "RESET!!" in html
    assert "2s steps(1,end)" in html
    assert dashboard.is_animated() is True
    assert dashboard.animation_seconds() == 2.0


def test_widget_is_registered():
    assert WIDGET_CLASSES["homeberry_dashboard"] is HomeberryDashboardWidget
