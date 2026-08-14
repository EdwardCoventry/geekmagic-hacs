"""Tests for the fullscreen Homeberry dashboard widget."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.geekmagic.htmldoc import CellContext, mdi_span
from custom_components.geekmagic.widgets import WIDGET_CLASSES, WidgetConfig
from custom_components.geekmagic.widgets.homeberry_dashboard import HomeberryDashboardWidget
from custom_components.geekmagic.widgets.state import EntityState, WidgetState
from custom_components.geekmagic.widgets.theme import DEFAULT_THEME

NOW = datetime(2026, 8, 11, 9, 42, tzinfo=UTC)
CTX = CellContext(width=240, height=240, slot_index=0, theme=DEFAULT_THEME)
WEATHER = "weather.forecast_home"
SCENE = "sensor.homeberry_runtime_active_scene"
CODEX = "sensor.codex_usage_codex_weekly_remaining"
INDOOR = "sensor.homeberry_runtime_indoor_temperature"
OUTDOOR = "sensor.homeberry_runtime_outdoor_temperature"
HEALTH = "sensor.homeberry_runtime_device_health"
SCENE_CHIPS = [
    {"id": "movie", "label": "Movie", "icon": "movie-open", "color": "#D477FF"},
    {
        "id": "curtains_close",
        "label": "Close",
        "icon": "curtains-closed",
        "color": "#72849A",
    },
    {"id": "lunch", "label": "Lunch", "icon": "food", "color": "#F4A261"},
    {"id": "pause", "label": "Pause", "icon": "pause", "color": "#A9ADB5"},
]


def widget() -> HomeberryDashboardWidget:
    return HomeberryDashboardWidget(
        WidgetConfig(
            widget_type="homeberry_dashboard",
            entity_id=CODEX,
            options={
                "weather_entity_id": WEATHER,
                "scene_entity_id": SCENE,
                "indoor_temperature_entity_id": INDOOR,
                "outdoor_temperature_entity_id": OUTDOOR,
                "health_entity_id": HEALTH,
            },
        )
    )


def state(quota: str = "68", *, activity_state: str = "used", celebration=False) -> WidgetState:
    return WidgetState(
        entity=EntityState(
            CODEX,
            quota,
            {"secondary_reset_at": (NOW + timedelta(days=3, hours=5)).timestamp()},
        ),
        entities={
            WEATHER: EntityState(WEATHER, "partlycloudy", {"temperature": 20}),
            SCENE: EntityState(
                SCENE,
                "Pause",
                {
                    "active_scene_id": "pause",
                    "scene_chips": SCENE_CHIPS,
                    "thermal_guidance": {
                        "kind": "window_open",
                        "icon": "window-open-variant",
                        "until_at": (NOW + timedelta(hours=4, minutes=18)).isoformat(),
                        "all_day": False,
                        "target_temperature_c": 21,
                    },
                    "codex_weekly_activity": {
                        "state": activity_state,
                        "celebration_active": celebration,
                    },
                },
            ),
            INDOOR: EntityState(INDOOR, "22.4", {"quality": "measured", "fallback": False}),
            OUTDOOR: EntityState(OUTDOOR, "27.6", {"quality": "measured", "fallback": False}),
            HEALTH: EntityState(
                HEALTH,
                "0",
                {
                    "category_counts": {"battery": 0, "connectivity": 0, "other": 0},
                    "overall_severity": "healthy",
                },
            ),
        },
        now=NOW,
    )


def test_dashboard_resolves_all_homeberry_glance_values():
    snapshot = widget().snapshot(state())

    assert snapshot.time_text == "09:42"
    assert snapshot.weekday_text == "TUE"
    assert snapshot.date_text == "11 AUG"
    assert [(item.label, item.value_text) for item in snapshot.temperatures] == [
        ("OUT", "28°"),
        ("IN", "22°"),
    ]
    assert snapshot.weather_condition == "partlycloudy"
    assert [chip.scene_id for chip in snapshot.scene_chips] == [
        "movie",
        "curtains_close",
        "lunch",
        "pause",
    ]
    assert snapshot.quota_remaining == 68
    assert snapshot.week_remaining == 46
    assert snapshot.reset_text == "3d 5h"


def test_dashboard_declares_all_entity_dependencies():
    assert widget().get_entities() == [CODEX, WEATHER, SCENE, INDOOR, OUTDOOR, HEALTH]


def test_dashboard_renders_scene_weather_and_quota():
    html = widget().render_html(CTX, state())

    assert "09:42" in html
    assert "TUE 11 AUG" in html
    assert "OUT" in html and "28°" in html
    assert "IN" in html and "22°" in html
    assert html.index("OUT") < html.index("IN")
    assert "PARTLY CLOUDY" not in html
    assert "hbd-weather-art" in html
    assert "Pause" in html and "Lunch" in html and "Close" in html
    assert "Movie" not in html
    assert "+1" in html
    assert html.index("Pause") < html.index("Lunch") < html.index("Close")
    assert "68%" in html
    assert "46%" in html
    assert '<span class="hbd-guidance-primary"><span>WINDOW</span><span>OPEN</span>' in html
    assert '<span class="hbd-guidance-detail"><span>UNTIL</span><span>2PM</span>' in html
    assert mdi_span("window-open-variant", "hbd-guidance-icon") in html
    assert mdi_span("calendar-clock", "hbd-week-icon") in html
    assert 'class="hbd-refresh"' in html
    assert "3d 5h" in html
    assert html.index("68%") < html.index("46%") < html.index("3d 5h")
    assert html.index("3d 5h") < html.index('class="hbd-bar"')
    assert 'class="hbd-codex-top"' in html
    assert mdi_span("movie-open", "hbd-chip-icon") not in html
    assert mdi_span("pause", "hbd-chip-icon") in html
    assert mdi_span("food", "hbd-chip-icon") in html
    assert mdi_span("curtains-closed", "hbd-chip-icon") in html
    assert ".hbd-dashboard{padding:4px" in html
    assert "grid-template-rows:172px 56px" in html
    assert "width:100%;display:flex;align-items:center;justify-content:space-between" in html
    assert "gap:1px;white-space:nowrap" in html
    assert "gap:2px;color:#C7CBD1" in html
    assert ".hbd-guidance-window_open,.hbd-guidance-window_keep_open{color:#F5F7FA;" in html
    assert "background:rgba(245,247,250,.12)" in html
    assert "height:41px;display:grid;grid-template-columns:20px max-content max-content" in html
    assert "grid-template-rows:22px 38px;row-gap:8px" in html
    assert "border:1px solid;border-radius:14px" in html
    assert "justify-self:center;align-self:center" in html
    assert ".hbd-guidance-primary,.hbd-guidance-detail{height:26px;display:grid" in html
    assert ".hbd-guidance-primary{font-size:13px;font-weight:1000" in html
    assert "justify-items:start;text-align:left" in html
    assert "justify-items:end;text-align:right" in html
    assert '<div class="hbd-climate-row"><div class="hbd-date-block">' in html
    assert '<div class="hbd-climate-row"><div class="hbd-guidance' in html
    assert "hbd-temperatures" not in html
    assert "hbd-codex-stats" not in html
    assert ".hbd-bar{height:23px" in html
    assert ".hbd-codex-top{width:100%;display:flex" in html
    assert "transform:translateY(-6px)" in html
    assert "transform:translateY(-7px)" in html
    assert "transform:translateY(-13px)" in html
    assert "grid-template-rows:65px 68px 39px" in html
    assert "grid-row:3;display:flex;align-items:center" in html
    assert ".hbd-climate-row:nth-child(2){transform:translateY(-4px)}" in html
    assert "border-bottom" not in html and "border-left" not in html
    assert "hbd-full-b" not in html.split("</style>", 1)[1]


@pytest.mark.parametrize(
    ("outdoor", "indoor", "outlined_labels"),
    [
        (27.6, 22.4, {"OUT"}),
        (18.2, 23.1, {"IN"}),
        (22.4, 22.3, set()),
    ],
)
def test_hottest_displayed_temperature_labels_are_outlined(outdoor, indoor, outlined_labels):
    current = state()
    current.entities[OUTDOOR] = EntityState(OUTDOOR, str(outdoor), {})
    current.entities[INDOOR] = EntityState(INDOOR, str(indoor), {})

    snapshot = widget().snapshot(current)
    assert {item.label for item in snapshot.temperatures if item.is_hottest} == (outlined_labels)

    html = widget().render_html(CTX, current)
    for label in ("OUT", "IN"):
        class_name = (
            "hbd-temperature-label hbd-temperature-hottest"
            if label in outlined_labels
            else "hbd-temperature-label"
        )
        assert f'<span class="{class_name}">{label}</span>' in html
    assert "hbd-temperature-value hbd-temperature-hottest" not in html
    assert ".hbd-temperature-hottest{color:#F5F7FA;background:#E5484D;" in html


@pytest.mark.parametrize(
    "missing_entities",
    [
        (INDOOR,),
        (OUTDOOR,),
        (INDOOR, OUTDOOR),
    ],
)
def test_unavailable_temperatures_do_not_receive_hotter_underlines(
    missing_entities,
):
    current = state()
    for entity_id in missing_entities:
        current.entities.pop(entity_id)

    snapshot = widget().snapshot(current)

    assert not any(item.is_hottest for item in snapshot.temperatures)


def test_full_quota_alternates_dashboard_and_reset_faces():
    dashboard = widget()
    html = dashboard.render_html(
        CTX,
        state("100", activity_state="fresh", celebration=True),
    )

    assert "hbd-dashboard" in html
    assert "CODEX" in html and "RESET!!" in html
    assert "2s steps(1,end)" in html
    assert dashboard.is_animated() is True
    assert dashboard.animation_seconds() == 2.0


@pytest.mark.parametrize(
    ("activity_state", "celebration"),
    [("used", False), ("unknown", False), ("fresh", False), ("unknown", True)],
)
def test_full_quota_does_not_flash_without_explicit_active_fresh_window(
    activity_state, celebration
):
    html = widget().render_html(
        CTX,
        state("100", activity_state=activity_state, celebration=celebration),
    )

    body = html.split("</style>", 1)[1]
    assert "hbd-dashboard" in body
    assert "RESET!!" not in body


@pytest.mark.parametrize("quota", ["1", "9", "10", "68", "99", "100"])
def test_codex_statistics_space_between_variable_width_values(quota):
    html = widget().render_html(CTX, state(quota))

    assert "justify-content:space-between" in html
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" not in html
    assert f">{quota}%</div>" in html


def test_widget_is_registered():
    assert WIDGET_CLASSES["homeberry_dashboard"] is HomeberryDashboardWidget


def test_missing_scene_metadata_is_explicitly_unavailable():
    current = state()
    current.entities[SCENE] = EntityState(SCENE, "Movie", {"active_scene_id": "movie"})

    html = widget().render_html(CTX, current)

    assert "NO SCENE DATA" in html
    assert mdi_span("alert-circle-outline", "hbd-chip-icon") in html


def test_missing_homeberry_temperatures_are_explicitly_unavailable():
    current = state()
    current.entities.pop(INDOOR)
    current.entities.pop(OUTDOOR)

    html = widget().render_html(CTX, current)

    assert html.count("--°") == 2


def test_fallback_temperature_has_question_mark_provenance():
    current = state()
    current.entities[OUTDOOR] = EntityState(
        OUTDOOR, "28.8", {"quality": "estimated", "fallback": True}
    )

    snapshot = widget().snapshot(current)

    assert snapshot.temperatures[0].label == "OUT?"
    html = widget().render_html(CTX, current)
    assert "OUT?" in html
    assert "width:max-content;min-width:30px" in html
    assert "padding:0 7px" in html


def test_health_chips_reserve_scene_width_and_show_category_counts():
    current = state()
    current.entities[HEALTH] = EntityState(
        HEALTH,
        "3",
        {
            "category_counts": {"battery": 1, "connectivity": 2, "other": 0},
            "overall_severity": "critical",
            "category_severity": {
                "battery": "critical",
                "connectivity": "warning",
                "other": "healthy",
            },
        },
    )

    html = widget().render_html(CTX, current)

    assert mdi_span("battery-alert", "hbd-chip-icon") in html
    assert mdi_span("wifi-alert", "hbd-chip-icon") in html
    assert "#E5484D" in html
    assert html.index('class="hbd-scene-lane"') < html.index('class="hbd-health-lane"')
    assert ".hbd-health-lane{justify-content:flex-end;margin-left:auto" in html


def test_health_chip_expands_into_available_right_side_space():
    current = state()
    current.entities[SCENE].attributes["scene_chips"] = [SCENE_CHIPS[-1]]
    current.entities[HEALTH] = EntityState(
        HEALTH,
        "1",
        {
            "category_counts": {"battery": 1, "connectivity": 0, "other": 0},
            "category_severity": {
                "battery": "warning",
                "connectivity": "healthy",
                "other": "healthy",
            },
        },
    )

    html = widget().render_html(CTX, current)

    assert "hbd-health-chip hbd-health-chip-expanded" in html
    assert '<span class="hbd-health-label">BATTERY</span>' in html
    assert html.index("Pause") < html.index("BATTERY")


def test_health_chip_names_the_device_and_problem_when_published():
    current = state()
    current.entities[SCENE].attributes["scene_chips"] = [SCENE_CHIPS[-1]]
    current.entities[HEALTH] = EntityState(
        HEALTH,
        "1",
        {
            "category_counts": {"battery": 0, "connectivity": 0, "other": 1},
            "category_severity": {
                "battery": "healthy",
                "connectivity": "healthy",
                "other": "warning",
            },
            "top_issues": [
                {
                    "asset_id": "device.temp",
                    "display_name": "Temp",
                    "category": "other",
                    "short_label": "Temp STALE",
                    "summary": "Temp: Data age is unknown",
                }
            ],
        },
    )

    html = widget().render_html(CTX, current)
    body = html.split("</style>", 1)[1]

    assert '<span class="hbd-health-label">TEMP STALE</span>' in body
    assert "OTHER" not in body
    assert '<span class="hbd-health-count">1</span>' not in body
    assert html.index("Pause") < html.index("TEMP STALE")


def test_health_chips_collapse_to_icon_and_count_when_row_is_full():
    current = state()
    current.entities[HEALTH] = EntityState(
        HEALTH,
        "6",
        {
            "category_counts": {"battery": 1, "connectivity": 2, "other": 3},
            "category_severity": {
                "battery": "critical",
                "connectivity": "warning",
                "other": "warning",
            },
        },
    )

    html = widget().render_html(CTX, current)

    body = html.split("</style>", 1)[1]
    assert "hbd-health-chip-expanded" not in body
    assert '<span class="hbd-health-label">' not in body
    assert "+3" in body


def test_week_remaining_tracks_remaining_fraction_of_week():
    just_reset = state()
    just_reset.entity.attributes["secondary_reset_at"] = (NOW + timedelta(days=7)).timestamp()
    reset_due = state()
    reset_due.entity.attributes["secondary_reset_at"] = NOW.timestamp()

    assert widget().snapshot(just_reset).week_remaining == 100
    assert widget().snapshot(reset_due).week_remaining == 0


def test_week_remaining_is_unavailable_without_reset_timestamp():
    current = state()
    current.entity.attributes.clear()

    snapshot = widget().snapshot(current)

    assert snapshot.week_remaining is None
    assert "--%" in widget().render_html(CTX, current)


def test_compact_thermal_guidance_variants_render_semantic_icons_and_text():
    cases = [
        (
            "window_open",
            "window-open-variant",
            ("WINDOW", "OPEN", "UNTIL", "2PM"),
            NOW.replace(hour=14, minute=0),
        ),
        ("window_closed", "window-closed-variant", ("WINDOW", "CLOSED"), None),
        ("heating", "radiator", ("HEATING", "TO 21°"), None),
        ("holding", "thermostat", ("HOLDING", "AT 21°"), None),
        (
            "heating_off",
            "radiator-off",
            ("HEATING", "OFF", "UNTIL", "2:30AM"),
            NOW.replace(hour=2, minute=30),
        ),
    ]
    for kind, icon, expected_parts, until_at in cases:
        current = state()
        current.entities[SCENE].attributes["thermal_guidance"] = {
            "kind": kind,
            "icon": icon,
            "until_at": None if until_at is None else until_at.isoformat(),
            "all_day": False,
            "target_temperature_c": 21,
        }

        html = widget().render_html(CTX, current)

        for expected in expected_parts:
            assert f"<span>{expected}</span>" in html
        assert mdi_span(icon, "hbd-guidance-icon") in html


def test_all_day_window_guidance_uses_compact_copy():
    current = state()
    current.entities[SCENE].attributes["thermal_guidance"]["all_day"] = True

    html = widget().render_html(CTX, current)

    assert '<span class="hbd-guidance-primary"><span>WINDOW</span><span>OPEN</span>' in html
    assert '<span class="hbd-guidance-detail"><span>ALL</span><span>DAY</span>' in html
