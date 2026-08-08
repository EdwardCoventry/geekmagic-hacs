"""Tests for the purpose-built Codex quota widget."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.geekmagic.htmldoc import CellContext
from custom_components.geekmagic.widgets import WIDGET_CLASSES, WIDGET_TYPE_SCHEMAS
from custom_components.geekmagic.widgets.base import WidgetConfig
from custom_components.geekmagic.widgets.codex_quota import (
    CodexQuotaWidget,
    QuotaMode,
    format_reset_countdown,
    parse_remaining_percent,
    quota_mode,
)
from custom_components.geekmagic.widgets.state import EntityState, WidgetState
from custom_components.geekmagic.widgets.theme import DEFAULT_THEME

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
CTX = CellContext(width=240, height=240, slot_index=0, theme=DEFAULT_THEME)


def entity(value: str, seconds: int = 2601) -> EntityState:
    return EntityState(
        "sensor.codex_weekly_remaining",
        value,
        {"secondary_reset_at": (NOW + timedelta(seconds=seconds)).timestamp()},
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("93", 93),
        ("5.4", 5),
        ("0", 0),
        ("120", 100),
        ("unknown", None),
        ("unavailable", None),
        ("bad", None),
    ],
)
def test_parse_remaining(value: str, expected: int | None) -> None:
    assert parse_remaining_percent(entity(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, QuotaMode.UNAVAILABLE),
        (100, QuotaMode.FULL),
        (21, QuotaMode.HEALTHY),
        (6, QuotaMode.WARNING),
        (1, QuotaMode.CRITICAL),
        (0, QuotaMode.EMPTY),
    ],
)
def test_mode_thresholds(value: int | None, expected: QuotaMode) -> None:
    assert quota_mode(value) is expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(90061, "1d 1h"), (3661, "1h 01m"), (61, "1m 01s"), (None, "--")],
)
def test_countdown_format(seconds: int | None, expected: str) -> None:
    assert format_reset_countdown(seconds) == expected


def widget() -> CodexQuotaWidget:
    return CodexQuotaWidget(
        WidgetConfig(widget_type="codex_quota", entity_id="sensor.codex_weekly_remaining")
    )


def render(value: str) -> str:
    return widget().render_html(CTX, WidgetState(entity=entity(value), now=NOW))


def test_unavailable_is_grey_dash_not_zero() -> None:
    html = render("unavailable")
    assert "--" in html
    assert ">0%<" not in html
    assert "cq-footer" not in html.split("</style>", 1)[1]


def test_real_zero_is_countdown_without_percent_or_footer() -> None:
    html = render("0")
    assert "43m 21s" in html
    assert ">0%<" not in html
    assert "cq-footer" not in html.split("</style>", 1)[1]


def test_normal_is_colored_percent_with_footer() -> None:
    html = render("93")
    assert ">93%<" in html
    assert "#39D353" in html
    assert 'stroke-width="38"' in html
    assert "cq-footer" in html.split("</style>", 1)[1]


def test_full_has_two_one_second_faces() -> None:
    quota = widget()
    html = quota.render_html(CTX, WidgetState(entity=entity("100"), now=NOW))
    assert ">100%<" in html
    assert "CODEX" in html and "RESET!!" in html
    assert "2s steps(1,end)" in html
    assert quota.is_animated() is True
    assert quota.animation_seconds() == 2.0


def test_widget_is_registered() -> None:
    assert WIDGET_CLASSES["codex_quota"] is CodexQuotaWidget
    assert WIDGET_TYPE_SCHEMAS["codex_quota"]["name"] == "Codex Weekly Quota"
