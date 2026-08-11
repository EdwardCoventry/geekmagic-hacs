"""Fullscreen Homeberry glance dashboard with Codex reset animation."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import mdi_span
from .base import Widget
from .codex_quota import (
    EMPTY_RING,
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
class HomeberryDashboardSnapshot:
    """Resolved values used by the dashboard renderer."""

    time_text: str
    date_text: str
    temperature_text: str
    weather_condition: str
    scene_text: str
    quota_remaining: int | None
    quota_mode: QuotaMode
    quota_color: str
    reset_text: str


class HomeberryDashboardWidget(Widget):
    """Render time, indoor climate, scene, and weekly Codex quota."""

    WIDGET_TYPE: ClassVar[str] = "homeberry_dashboard"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Homeberry Dashboard",
        "needs_entity": True,
        "entity_domains": ["sensor"],
        "options": [
            {
                "key": "temperature_entity_id",
                "type": "entity",
                "label": "Temperature entity",
                "domains": ["sensor"],
                "required": True,
            },
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
        for key in ("temperature_entity_id", "weather_entity_id", "scene_entity_id"):
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
        temperature = self._additional(state, "temperature_entity_id")
        weather = self._additional(state, "weather_entity_id")
        scene = self._additional(state, "scene_entity_id")

        temperature_text = "--°"
        if temperature is not None:
            with suppress(TypeError, ValueError):
                temperature_text = f"{round(float(temperature.state))}°"

        condition = str(weather.state if weather is not None else "unknown").strip().lower()
        if condition in {"", "unknown", "unavailable"}:
            condition = "unknown"

        scene_value = str(scene.state if scene is not None else "unknown").strip()
        scene_text = (
            "NO SCENE"
            if scene_value.lower() in {"", "unknown", "unavailable"}
            else scene_value.upper()
        )

        remaining = parse_remaining_percent(state.entity)
        mode = quota_mode(remaining)
        reset_at = resolve_reset_at(
            state.entity,
            reset_at_attribute=self.config.options.get(
                "reset_at_attribute", "secondary_reset_at"
            ),
        )
        return HomeberryDashboardSnapshot(
            time_text=now.strftime("%H:%M"),
            date_text=now.strftime("%a %d %b").upper(),
            temperature_text=temperature_text,
            weather_condition=condition,
            scene_text=scene_text,
            quota_remaining=remaining,
            quota_mode=mode,
            quota_color=color_for_mode(mode),
            reset_text=format_reset_countdown(seconds_until(reset_at, now)),
        )

    @staticmethod
    def _quota_parts(snapshot: HomeberryDashboardSnapshot) -> tuple[str, str]:
        if snapshot.quota_mode is QuotaMode.UNAVAILABLE:
            percent = 0
            percent_text = "--%"
            color = EMPTY_RING
        else:
            percent = snapshot.quota_remaining or 0
            percent_text = f"{percent}%"
            color = snapshot.quota_color
        return (
            f'<div class="hbd-percent" style="color:{color}">{percent_text}</div>',
            '<div class="hbd-bar"><div class="hbd-bar-fill" '
            f'style="width:{percent}%;background:{color}"></div></div>',
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

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        del ctx
        snapshot = self.snapshot(state)
        weather_art = self._weather_art(snapshot.weather_condition)
        home_icon = mdi_span("home-lightbulb", "hbd-home-icon")
        reset_icon = (
            '<svg class="hbd-refresh" viewBox="0 0 20 20" aria-hidden="true">'
            '<path d="M16.5 6.5A7 7 0 1 0 17 14" fill="none" '
            'stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'
            '<path d="M16.5 2.5v4.5H12" fill="none" stroke="currentColor" '
            'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
            "</svg>"
        )
        reset_text = snapshot.reset_text
        quota_percent, quota_bar = self._quota_parts(snapshot)
        css = """
<style>
.hbd{position:absolute;inset:0;overflow:hidden;background:#000;color:#f5f7fa;
font-family:'Nunito','DejaVu Sans',sans-serif;font-weight:900}
.hbd-dashboard,.hbd-reset{position:absolute;inset:0}
.hbd-dashboard{padding:7px 13px 8px;box-sizing:border-box}
.hbd-hero{height:168px;display:grid;grid-template-columns:minmax(0,1fr) 76px}
.hbd-clock{display:grid;grid-template-rows:87px 29px 39px;align-content:center;
padding:0 8px 0 1px;
box-sizing:border-box}
.hbd-time{font-family:'Nunito','DejaVu Sans',sans-serif;font-size:70px;font-weight:700;
font-variant-numeric:tabular-nums;line-height:.88;letter-spacing:-5px;align-self:end}
.hbd-date{font-size:17px;line-height:1;margin-top:5px;color:#C7CBD1;letter-spacing:1.2px;
align-self:start}
.hbd-weather{display:grid;grid-template-rows:87px 42px 26px;align-content:center;
justify-items:center;box-sizing:border-box}
.hbd-weather-art{width:64px;height:64px;display:block;align-self:end}
.hbd-temp{font-size:38px;line-height:1;margin-top:4px;color:#F5F7FA;letter-spacing:-2px;
align-self:start}
.hbd-scene{display:flex;align-items:center;align-self:center;gap:8px;min-width:0}
.hbd-home-icon{font-family:'Material Design Icons';font-size:25px;line-height:1;color:#C7CBD1}
.hbd-scene-name{font-size:22px;line-height:1;letter-spacing:.7px;white-space:nowrap;overflow:hidden}
.hbd-codex{height:57px;display:grid;grid-template-rows:31px 18px;row-gap:4px}
.hbd-codex-top{display:flex;align-items:center;justify-content:space-between}
.hbd-bar{height:18px;width:100%;border-radius:11px;background:#2F3136;overflow:hidden}
.hbd-bar-fill{height:100%;border-radius:9px}
.hbd-percent{font-size:28px;line-height:1;text-align:left;letter-spacing:-1.5px}
.hbd-reset-count{display:flex;align-items:center;gap:4px;color:#C7CBD1;font-size:18px;
line-height:1;white-space:nowrap}
.hbd-refresh{width:19px;height:19px;display:block;flex:0 0 auto}
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
            '<div class="hbd-hero"><div class="hbd-clock">'
            f'<div class="hbd-time">{snapshot.time_text}</div>'
            f'<div class="hbd-date">{snapshot.date_text}</div>'
            f'<div class="hbd-scene">{home_icon}'
            f'<div class="hbd-scene-name">{escape(snapshot.scene_text)}</div></div></div>'
            f'<div class="hbd-weather">{weather_art}'
            f'<div class="hbd-temp">{escape(snapshot.temperature_text)}</div></div></div>'
            f'<div class="hbd-codex"><div class="hbd-codex-top">{quota_percent}'
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
