"""Fullscreen Homeberry glance dashboard with Codex reset animation."""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import mdi_span
from .base import Widget
from .codex_quota import (
    EMPTY_RING,
    TRACK,
    QuotaMode,
    color_for_mode,
    format_reset_countdown,
    parse_remaining_percent,
    quota_mode,
    resolve_reset_at,
    seconds_until,
)

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import EntityState, WidgetState


@dataclass(frozen=True)
class SceneChipSnapshot:
    """One Homeberry scene chip, in canonical queue order."""

    scene_id: str
    label: str
    icon: str
    color: str


@dataclass(frozen=True)
class TemperatureSnapshot:
    """One explicitly located Homeberry temperature reading."""

    label: str
    value_text: str
    is_hottest: bool


@dataclass(frozen=True)
class ThermalGuidanceSnapshot:
    """Semantic thermal guidance published by Homeberry."""

    kind: str
    icon: str
    until_at: datetime | None
    all_day: bool
    target_temperature_c: float | None


@dataclass(frozen=True)
class HomeberryDashboardSnapshot:
    """Resolved values used by the dashboard renderer."""

    time_text: str
    weekday_text: str
    date_text: str
    temperatures: tuple[TemperatureSnapshot, TemperatureSnapshot]
    weather_condition: str
    scene_chips: tuple[SceneChipSnapshot, ...]
    thermal_guidance: ThermalGuidanceSnapshot
    quota_remaining: int | None
    quota_mode: QuotaMode
    quota_color: str
    week_remaining: int | None
    reset_text: str


class HomeberryDashboardWidget(Widget):
    """Render time, indoor climate, scene, and weekly Codex quota."""

    WIDGET_TYPE: ClassVar[str] = "homeberry_dashboard"
    _HEX_COLOR: ClassVar[re.Pattern[str]] = re.compile(r"^#[0-9a-fA-F]{6}$")
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Homeberry Dashboard",
        "needs_entity": True,
        "entity_domains": ["sensor"],
        "options": [
            {
                "key": "weather_entity_id",
                "type": "entity",
                "label": "Weather entity",
                "domains": ["weather"],
                "required": True,
            },
            {
                "key": "scene_entity_id",
                "type": "entity",
                "label": "Homeberry scene entity",
                "domains": ["sensor"],
                "required": True,
            },
            {
                "key": "reset_at_attribute",
                "type": "text",
                "label": "Codex reset timestamp attribute",
                "default": "secondary_reset_at",
            },
        ],
    }

    def get_entities(self) -> list[str]:
        entities = super().get_entities()
        for key in ("weather_entity_id", "scene_entity_id"):
            entity_id = str(self.config.options.get(key) or "").strip()
            if entity_id:
                entities.append(entity_id)
        return entities

    def is_animated(self) -> bool:
        """The full state alternates between dashboard and reset faces."""
        return True

    def animation_seconds(self) -> float:
        return 2.0

    def _additional(self, state: WidgetState, key: str) -> EntityState | None:
        entity_id = str(self.config.options.get(key) or "").strip()
        return state.entities.get(entity_id)

    def snapshot(self, state: WidgetState) -> HomeberryDashboardSnapshot:
        now = state.now or datetime.now(tz=UTC)
        weather = self._additional(state, "weather_entity_id")
        scene = self._additional(state, "scene_entity_id")

        resolved_temperatures: list[tuple[str, int | None]] = []
        for label, attribute in (
            ("OUT", "outdoor_temperature_c"),
            ("IN", "indoor_temperature_c"),
        ):
            display_temperature = None
            if scene is not None:
                with suppress(TypeError, ValueError):
                    raw_temperature = scene.attributes.get(attribute)
                    if raw_temperature is not None:
                        display_temperature = round(float(raw_temperature))
            resolved_temperatures.append((label, display_temperature))

        available_temperatures = [
            value for _, value in resolved_temperatures if value is not None
        ]
        hottest_temperature = (
            max(available_temperatures)
            if len(available_temperatures) == len(resolved_temperatures)
            else None
        )
        temperatures = [
            TemperatureSnapshot(
                label=label,
                value_text=f"{value}°" if value is not None else "--°",
                is_hottest=value is not None and value == hottest_temperature,
            )
            for label, value in resolved_temperatures
        ]

        condition = str(weather.state if weather is not None else "unknown").strip().lower()
        if condition in {"", "unknown", "unavailable"}:
            condition = "unknown"

        scene_chips: list[SceneChipSnapshot] = []
        raw_scene_chips = scene.attributes.get("scene_chips") if scene is not None else None
        if isinstance(raw_scene_chips, list):
            for raw_chip in raw_scene_chips:
                if not isinstance(raw_chip, dict):
                    continue
                scene_id = str(raw_chip.get("id") or "").strip()
                label = str(raw_chip.get("label") or "").strip()
                icon = str(raw_chip.get("icon") or "").strip()
                color = str(raw_chip.get("color") or "").strip()
                if not (scene_id and label and icon):
                    continue
                scene_chips.append(
                    SceneChipSnapshot(
                        scene_id=scene_id,
                        label=label,
                        icon=icon,
                        color=color if self._HEX_COLOR.fullmatch(color) else EMPTY_RING,
                    )
                )
        if not scene_chips:
            scene_chips.append(
                SceneChipSnapshot(
                    scene_id="unavailable",
                    label="NO SCENE DATA",
                    icon="alert-circle-outline",
                    color=EMPTY_RING,
                )
            )

        raw_guidance = scene.attributes.get("thermal_guidance") if scene is not None else None
        guidance = self._thermal_guidance_snapshot(raw_guidance)

        remaining = parse_remaining_percent(state.entity)
        mode = quota_mode(remaining)
        reset_at = resolve_reset_at(
            state.entity,
            reset_at_attribute=self.config.options.get(
                "reset_at_attribute", "secondary_reset_at"
            ),
        )
        reset_seconds = seconds_until(reset_at, now)
        week_remaining = None
        if reset_seconds is not None:
            week_seconds = 7 * 24 * 60 * 60
            remaining_seconds = max(0.0, min(float(week_seconds), reset_seconds))
            week_remaining = round(100 * remaining_seconds / week_seconds)
        return HomeberryDashboardSnapshot(
            time_text=now.strftime("%H:%M"),
            weekday_text=now.strftime("%a").upper(),
            date_text=now.strftime("%d %b").upper(),
            temperatures=(temperatures[0], temperatures[1]),
            weather_condition=condition,
            scene_chips=tuple(scene_chips),
            thermal_guidance=guidance,
            quota_remaining=remaining,
            quota_mode=mode,
            quota_color=color_for_mode(mode),
            week_remaining=week_remaining,
            reset_text=format_reset_countdown(reset_seconds),
        )

    @staticmethod
    def _quota_parts(snapshot: HomeberryDashboardSnapshot) -> tuple[str, str, str]:
        if snapshot.quota_mode is QuotaMode.UNAVAILABLE:
            percent = 0
            percent_text = "--%"
            color = EMPTY_RING
        else:
            percent = snapshot.quota_remaining or 0
            percent_text = f"{percent}%"
            color = snapshot.quota_color
        week_text = "--%" if snapshot.week_remaining is None else f"{snapshot.week_remaining}%"
        week_icon = mdi_span("calendar-clock", "hbd-week-icon")
        return (
            f'<div class="hbd-percent" style="color:{color}">{percent_text}</div>',
            f'<div class="hbd-week-progress">{week_icon}<span>{week_text}</span></div>',
            '<div class="hbd-bar"><div class="hbd-bar-fill" '
            f'style="width:{percent}%;background:{color}"></div></div>',
        )

    @staticmethod
    def _thermal_guidance_snapshot(raw: Any) -> ThermalGuidanceSnapshot:
        if not isinstance(raw, dict):
            return ThermalGuidanceSnapshot(
                kind="unavailable",
                icon="thermometer-alert",
                until_at=None,
                all_day=False,
                target_temperature_c=None,
            )
        until_at = None
        raw_until = raw.get("until_at")
        if raw_until:
            with suppress(TypeError, ValueError):
                until_at = datetime.fromisoformat(str(raw_until))
        target = None
        with suppress(TypeError, ValueError):
            raw_target = raw.get("target_temperature_c")
            if raw_target is not None:
                target = float(raw_target)
        return ThermalGuidanceSnapshot(
            kind=str(raw.get("kind") or "unavailable"),
            icon=str(raw.get("icon") or "thermometer-alert"),
            until_at=until_at,
            all_day=bool(raw.get("all_day")),
            target_temperature_c=target,
        )

    @staticmethod
    def _guidance_time(value: datetime) -> str:
        hour = value.strftime("%I").lstrip("0") or "0"
        minute = value.strftime("%M")
        suffix = value.strftime("%p")
        return f"{hour}{suffix}" if minute == "00" else f"{hour}:{minute}{suffix}"

    def _thermal_guidance_html(self, snapshot: HomeberryDashboardSnapshot) -> str:
        guidance = snapshot.thermal_guidance
        kind = guidance.kind
        primary = ("STATUS", "UNKNOWN")
        detail: tuple[str, str] | None = None
        if kind in {"window_open", "window_keep_open"}:
            primary = ("WINDOW", "OPEN")
            if guidance.all_day:
                detail = ("ALL", "DAY")
            elif guidance.until_at is not None:
                detail = ("UNTIL", self._guidance_time(guidance.until_at))
        elif kind == "window_closed":
            primary = ("WINDOW", "CLOSED")
        elif kind == "heating":
            target = (
                "--°"
                if guidance.target_temperature_c is None
                else f"{round(guidance.target_temperature_c)}°"
            )
            primary = ("HEATING", f"TO {target}")
        elif kind == "holding":
            target = (
                "--°"
                if guidance.target_temperature_c is None
                else f"{round(guidance.target_temperature_c)}°"
            )
            primary = ("HOLDING", f"AT {target}")
        elif kind == "heating_off":
            primary = ("HEATING", "OFF")
            if guidance.until_at is not None:
                detail = ("UNTIL", self._guidance_time(guidance.until_at))
        else:
            kind = "unavailable"
        primary_html = (
            '<span class="hbd-guidance-primary">'
            f"<span>{escape(primary[0])}</span><span>{escape(primary[1])}</span></span>"
        )
        detail_html = ""
        if detail is not None:
            detail_html = (
                '<span class="hbd-guidance-detail">'
                f"<span>{escape(detail[0])}</span>"
                f"<span>{escape(detail[1])}</span></span>"
            )
        return (
            f'<div class="hbd-guidance hbd-guidance-{escape(kind)}">'
            f'{mdi_span(guidance.icon, "hbd-guidance-icon")}'
            f"{primary_html}{detail_html}</div>"
        )

    @staticmethod
    def _weather_art(condition: str) -> str:
        """Return a compact illustrated SVG for the current condition."""
        svg_start = (
            '<svg class="hbd-weather-art" viewBox="0 0 64 64">'
            '<defs><linearGradient id="hbd-sun" x1="0" y1="0" x2="1" y2="1">'
            '<stop stop-color="#FFD76A"/><stop offset="1" stop-color="#FF9F0A"/>'
            '</linearGradient><linearGradient id="hbd-cloud" x1="0" y1="0" x2="0" y2="1">'
            '<stop stop-color="#F4F7FB"/><stop offset="1" stop-color="#91A0B4"/>'
            '</linearGradient></defs>'
        )
        sun = (
            '<g stroke="#FFD76A" stroke-width="3" stroke-linecap="round">'
            '<path d="M42 3v6M42 35v6M24 21h6M54 21h6M29 8l4 4M51 30l4 4M55 8l-4 4M33 30l-4 4"/>'
            '</g><circle cx="42" cy="21" r="10" fill="url(#hbd-sun)"/>'
        )
        cloud = (
            '<g fill="url(#hbd-cloud)"><circle cx="25" cy="39" r="10"/>'
            '<circle cx="36" cy="33" r="14"/><circle cx="49" cy="40" r="9"/>'
            '<rect x="16" y="39" width="42" height="12" rx="6"/></g>'
        )
        if condition in {"sunny", "clear"}:
            body = sun
        elif condition == "clear-night":
            body = (
                '<path d="M46 46A22 22 0 1 1 35 7a18 18 0 1 0 11 39Z" '
                'fill="#A9C7FF"/><circle cx="48" cy="13" r="2" fill="#fff"/>'
                '<circle cx="55" cy="24" r="1.5" fill="#fff"/>'
            )
        else:
            body = (sun if condition == "partlycloudy" else "") + cloud
            if condition in {"rainy", "pouring"}:
                body += (
                    '<g stroke="#5AC8FA" stroke-width="3" stroke-linecap="round">'
                    '<path d="M24 55l-3 5M36 55l-3 5M48 55l-3 5"/></g>'
                )
            elif condition in {"snowy", "snowy-rainy"}:
                body += (
                    '<g fill="#D8F3FF"><circle cx="24" cy="58" r="2"/>'
                    '<circle cx="37" cy="56" r="2"/>'
                    '<circle cx="50" cy="59" r="2"/></g>'
                )
            elif condition in {"lightning", "lightning-rainy"}:
                body += '<path d="M37 49h9l-7 9h6L32 64l4-10h-6Z" fill="#FFD60A"/>'
            elif condition == "fog":
                body += (
                    '<g stroke="#C7CBD1" stroke-width="3" stroke-linecap="round">'
                    '<path d="M14 55h38M20 61h30"/></g>'
                )
            elif condition == "unknown":
                body += (
                    '<text x="37" y="45" text-anchor="middle" fill="#2F3136" '
                    'font-size="18" font-weight="900">?</text>'
                )
        return svg_start + body + "</svg>"

    @staticmethod
    def _chip_background(color: str) -> str:
        red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
        return f"rgba({red},{green},{blue},.18)"

    def _scene_chips_html(self, snapshot: HomeberryDashboardSnapshot) -> str:
        """Render newest three queued scenes and summarize older entries."""
        visible = tuple(reversed(snapshot.scene_chips[-3:]))
        parts: list[str] = []
        for chip in visible:
            color = chip.color
            parts.append(
                '<div class="hbd-chip" '
                f'style="color:{color};border-color:{color};'
                f'background:{self._chip_background(color)}">'
                f'{mdi_span(chip.icon, "hbd-chip-icon")}'
                f'<span class="hbd-chip-label">{escape(chip.label)}</span></div>'
            )
        overflow = len(snapshot.scene_chips) - len(visible)
        if overflow:
            parts.append(
                f'<div class="hbd-chip-more" style="background:{TRACK}">+{overflow}</div>'
            )
        return "".join(parts)

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        del ctx
        snapshot = self.snapshot(state)
        weather_art = self._weather_art(snapshot.weather_condition)
        scene_chips = self._scene_chips_html(snapshot)
        thermal_guidance = self._thermal_guidance_html(snapshot)
        temperature_rows = []
        for item in snapshot.temperatures:
            hottest_class = " hbd-temperature-hottest" if item.is_hottest else ""
            underline = (
                '<span class="hbd-temperature-underline"></span>'
                if item.is_hottest
                else ""
            )
            temperature_rows.append(
                '<div class="hbd-temperature">'
                f'<span class="hbd-temperature-label{hottest_class}">'
                f'<span>{item.label}</span>{underline}</span>'
                f'<span class="hbd-temperature-value">{escape(item.value_text)}</span>'
                '</div>'
            )
        outdoor_temperature, indoor_temperature = temperature_rows
        reset_icon = (
            '<svg class="hbd-refresh" viewBox="0 0 20 20" aria-hidden="true">'
            '<path d="M16.5 6.5A7 7 0 1 0 17 14" fill="none" '
            'stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'
            '<path d="M16.5 2.5v4.5H12" fill="none" stroke="currentColor" '
            'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
            "</svg>"
        )
        reset_text = snapshot.reset_text
        quota_percent, week_remaining, quota_bar = self._quota_parts(snapshot)
        css = """
<style>
.hbd{position:absolute;inset:0;overflow:hidden;background:#000;color:#f5f7fa;
font-family:'Nunito','DejaVu Sans',sans-serif;font-weight:900}
.hbd-dashboard,.hbd-reset{position:absolute;inset:0}
.hbd-dashboard{padding:4px 8px 8px;box-sizing:border-box;display:grid;
grid-template-rows:157px 67px;
row-gap:4px}
.hbd-hero{display:grid;grid-template-columns:minmax(0,1fr) 64px;
grid-template-rows:62px 59px 36px;min-width:0}
.hbd-time{grid-column:1;grid-row:1;font-family:'Nunito','DejaVu Sans',sans-serif;
font-size:74px;font-weight:700;font-variant-numeric:tabular-nums;line-height:.88;
letter-spacing:-5.5px;align-self:end}
.hbd-climate-rows{grid-column:1/-1;grid-row:2;align-self:stretch;display:grid;
grid-template-rows:22px 30px;row-gap:7px;min-width:0}
.hbd-climate-row{display:flex;align-items:center;justify-content:space-between;min-width:0}
.hbd-date-block{height:22px;color:#C7CBD1;font-size:18px;line-height:1;
letter-spacing:.8px;display:flex;align-items:center;white-space:nowrap}
.hbd-guidance{height:30px;display:grid;grid-template-columns:18px max-content max-content;
align-items:center;column-gap:4px;padding:0 5px 0 4px;
border:1px solid;border-radius:14px;box-sizing:border-box;font-size:15px;line-height:1;
white-space:nowrap;min-width:0;overflow:hidden}
.hbd-guidance-icon{font-family:'Material Design Icons';font-size:18px;line-height:1;
justify-self:center;align-self:center}
.hbd-guidance-primary,.hbd-guidance-detail{height:22px;display:grid;
grid-template-rows:repeat(2,1fr);align-items:center;row-gap:0;line-height:1}
.hbd-guidance-primary>span,.hbd-guidance-detail>span{display:flex;align-items:center;height:11px}
.hbd-guidance-primary{font-size:11px;font-weight:1000;letter-spacing:.15px;
justify-items:start;text-align:left}
.hbd-guidance-detail{font-size:10px;font-weight:900;letter-spacing:.2px;
justify-items:end;text-align:right}
.hbd-guidance-window_open,.hbd-guidance-window_keep_open{color:#F5F7FA;
background:rgba(245,247,250,.12)}
.hbd-guidance-window_closed,.hbd-guidance-heating_off,.hbd-guidance-unavailable{
color:#C7CBD1;background:rgba(199,203,209,.12)}
.hbd-guidance-heating{color:#FF9F0A;background:rgba(255,159,10,.18)}
.hbd-guidance-holding{color:#39D353;background:rgba(57,211,83,.18)}
.hbd-weather-art{grid-column:2;grid-row:1;width:62px;height:62px;display:block;
align-self:end;justify-self:end}
.hbd-temperature{height:24px;display:flex;align-items:flex-end;justify-content:flex-end;gap:4px}
.hbd-temperature-label{position:relative;font-size:16px;line-height:1;letter-spacing:.5px;
padding-bottom:2px}
.hbd-temperature-underline{position:absolute;left:0;right:.5px;bottom:-1px;height:2px;
background:currentColor;border-radius:1px}
.hbd-temperature-value{font-size:32px;line-height:.8;letter-spacing:-1.5px;min-width:48px;
text-align:right}
.hbd-scene{grid-column:1/-1;grid-row:3;display:flex;align-items:end;gap:4px;
min-width:0;overflow:hidden}
.hbd-chip{height:27px;display:flex;align-items:center;gap:2px;padding:0 6px 0 4px;
border:1px solid;border-radius:14px;box-sizing:border-box;min-width:0;flex:0 1 auto}
.hbd-chip-icon{font-family:'Material Design Icons';font-size:15px;line-height:1;flex:0 0 auto}
.hbd-chip-label{font-size:13px;line-height:1;letter-spacing:.1px;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.hbd-chip-more{height:27px;min-width:27px;padding:0 5px;border-radius:14px;
color:#C7CBD1;display:flex;align-items:center;justify-content:center;font-size:13px;
line-height:1;box-sizing:border-box;flex:0 0 auto}
.hbd-codex{height:67px;display:grid;grid-template-rows:34px 23px;row-gap:3px;
align-content:center}
.hbd-codex-top{width:100%;display:flex;align-items:center;justify-content:space-between;
transform:translateY(-7px)}
.hbd-bar{height:30px;width:100%;border-radius:15px;background:#2F3136;overflow:hidden;
transform:translateY(-7px)}
.hbd-bar-fill{height:100%;border-radius:15px}
.hbd-percent{font-size:30px;line-height:1;text-align:left;letter-spacing:-1.5px;
flex:0 0 auto}
.hbd-week-progress{color:#C7CBD1;font-size:19px;line-height:1;display:flex;
align-items:center;gap:1px;white-space:nowrap;flex:0 0 auto}
.hbd-week-icon{font-family:'Material Design Icons';font-size:20px;line-height:1}
.hbd-reset-count{display:flex;align-items:center;gap:2px;color:#C7CBD1;font-size:19px;
line-height:1;white-space:nowrap;flex:0 0 auto}
.hbd-refresh{width:20px;height:20px;display:block;flex:0 0 auto}
.hbd-full-a,.hbd-full-b{position:absolute;inset:0}
.hbd-full-a{animation:hbd-a 2s steps(1,end) infinite}
.hbd-full-b{animation:hbd-b 2s steps(1,end) infinite}
.hbd-reset{display:flex;flex-direction:column;align-items:center;justify-content:center;
color:#39D353;font-size:58px;line-height:.92;letter-spacing:-3px;text-align:center}
@keyframes hbd-a{0%,49.99%{opacity:1}50%,100%{opacity:0}}
@keyframes hbd-b{0%,49.99%{opacity:0}50%,100%{opacity:1}}
</style>
"""
        dashboard = (
            '<div class="hbd-dashboard">'
            '<div class="hbd-hero">'
            f'<div class="hbd-time">{snapshot.time_text}</div>'
            f'{weather_art}<div class="hbd-climate-rows">'
            f'<div class="hbd-climate-row"><div class="hbd-date-block">'
            f'{snapshot.weekday_text} {snapshot.date_text}</div>{outdoor_temperature}</div>'
            f'<div class="hbd-climate-row">{thermal_guidance}{indoor_temperature}</div>'
            '</div>'
            f'<div class="hbd-scene">{scene_chips}</div></div>'
            '<div class="hbd-codex"><div class="hbd-codex-top">'
            f'{quota_percent}{week_remaining}'
            f'<div class="hbd-reset-count">{reset_icon}{escape(reset_text)}</div></div>'
            f'{quota_bar}</div></div>'
        )
        if snapshot.quota_mode is not QuotaMode.FULL:
            return css + f'<div class="hbd">{dashboard}</div>'
        reset = '<div class="hbd-reset"><div>CODEX</div><div>RESET!!</div></div>'
        return (
            css
            + f'<div class="hbd"><div class="hbd-full-a">{dashboard}</div>'
            + f'<div class="hbd-full-b">{reset}</div></div>'
        )
