"""Fullscreen weekly Codex remaining-quota widget."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from .base import Widget
from .state import EntityState

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState

BACKGROUND = "#000000"
TRACK = "#2F3136"
EMPTY_RING = "#9A9DA3"
HEALTHY_GREEN = "#39D353"
WARNING_AMBER = "#E6A23C"
CRITICAL_RED = "#E5484D"
FOOTER_GREY = "#C7CBD1"
EMPTY_TEXT = "#EBEDF0"


class QuotaMode(StrEnum):
    """Visual modes for remaining quota."""

    UNAVAILABLE = "unavailable"
    FULL = "full"
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    EMPTY = "empty"


def parse_remaining_percent(entity: EntityState | None) -> int | None:
    """Parse the already-remaining percentage without inverting it."""
    if entity is None or str(entity.state).lower() in {"unknown", "unavailable"}:
        return None
    try:
        value = float(entity.state)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return max(0, min(100, round(value)))


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def resolve_reset_at(
    entity: EntityState | None,
    *,
    reset_at_attribute: str = "secondary_reset_at",
    reset_after_attribute: str = "secondary_reset_after_seconds",
    captured_at_attribute: str = "captured_at",
) -> datetime | None:
    """Resolve an absolute reset timestamp from stable state attributes."""
    if entity is None:
        return None
    raw_reset_at = entity.get(reset_at_attribute)
    if raw_reset_at is not None and not isinstance(raw_reset_at, bool):
        try:
            epoch = float(raw_reset_at)
            if math.isfinite(epoch):
                return datetime.fromtimestamp(epoch, tz=UTC)
        except (OSError, OverflowError, TypeError, ValueError):
            pass
    raw_after = entity.get(reset_after_attribute)
    raw_captured = entity.get(captured_at_attribute)
    if raw_after is None or raw_captured is None or isinstance(raw_after, bool):
        return None
    try:
        after_seconds = float(raw_after)
        captured = datetime.fromisoformat(str(raw_captured))
        if math.isfinite(after_seconds):
            return _aware(captured) + timedelta(seconds=after_seconds)
    except (OverflowError, TypeError, ValueError):
        pass
    return None


def seconds_until(reset_at: datetime | None, now: datetime) -> int | None:
    """Return whole non-negative seconds until reset."""
    if reset_at is None:
        return None
    return max(0, math.floor((_aware(reset_at) - _aware(now)).total_seconds()))


def format_reset_countdown(seconds: int | None) -> str:
    """Format countdown at the requested precision."""
    if seconds is None:
        return "--"
    seconds = max(0, seconds)
    if seconds >= 86_400:
        days, remainder = divmod(seconds, 86_400)
        return f"{days}d {remainder // 3_600}h"
    if seconds >= 3_600:
        hours, remainder = divmod(seconds, 3_600)
        return f"{hours}h {remainder // 60:02d}m"
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}m {remainder:02d}s"


def quota_mode(remaining: int | None) -> QuotaMode:
    if remaining is None:
        return QuotaMode.UNAVAILABLE
    if remaining == 100:
        return QuotaMode.FULL
    if remaining >= 21:
        return QuotaMode.HEALTHY
    if remaining >= 6:
        return QuotaMode.WARNING
    if remaining >= 1:
        return QuotaMode.CRITICAL
    return QuotaMode.EMPTY


def color_for_mode(mode: QuotaMode) -> str:
    return {
        QuotaMode.UNAVAILABLE: EMPTY_RING,
        QuotaMode.FULL: HEALTHY_GREEN,
        QuotaMode.HEALTHY: HEALTHY_GREEN,
        QuotaMode.WARNING: WARNING_AMBER,
        QuotaMode.CRITICAL: CRITICAL_RED,
        QuotaMode.EMPTY: EMPTY_RING,
    }[mode]


@dataclass(frozen=True)
class CodexQuotaSnapshot:
    remaining_percent: int | None
    reset_seconds: int | None
    reset_text: str
    mode: QuotaMode
    color: str


class CodexQuotaWidget(Widget):
    """Render a deliberately minimal weekly quota face."""

    WIDGET_TYPE: ClassVar[str] = "codex_quota"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Codex Weekly Quota",
        "needs_entity": True,
        "entity_domains": ["sensor"],
        "options": [
            {
                "key": "reset_at_attribute",
                "type": "text",
                "label": "Reset timestamp attribute",
                "default": "secondary_reset_at",
            },
            {
                "key": "reset_after_attribute",
                "type": "text",
                "label": "Reset seconds attribute",
                "default": "secondary_reset_after_seconds",
            },
            {
                "key": "captured_at_attribute",
                "type": "text",
                "label": "Captured timestamp attribute",
                "default": "captured_at",
            },
        ],
    }

    def is_animated(self) -> bool:
        """Allow the 100% face to alternate once per second."""
        return True

    def animation_seconds(self) -> float:
        return 2.0

    def snapshot(self, state: WidgetState) -> CodexQuotaSnapshot:
        now = state.now or datetime.now(tz=UTC)
        remaining = parse_remaining_percent(state.entity)
        reset_at = resolve_reset_at(
            state.entity,
            reset_at_attribute=self.config.options.get("reset_at_attribute", "secondary_reset_at"),
            reset_after_attribute=self.config.options.get(
                "reset_after_attribute", "secondary_reset_after_seconds"
            ),
            captured_at_attribute=self.config.options.get("captured_at_attribute", "captured_at"),
        )
        reset_seconds = seconds_until(reset_at, now)
        mode = quota_mode(remaining)
        return CodexQuotaSnapshot(
            remaining_percent=remaining,
            reset_seconds=reset_seconds,
            reset_text=format_reset_countdown(reset_seconds),
            mode=mode,
            color=color_for_mode(mode),
        )

    @staticmethod
    def _ring(percent: int, color: str, *, center_y: int = 104, radius: int = 82) -> str:
        circumference = 2 * math.pi * radius
        offset = circumference * (1 - percent / 100)
        return (
            f'<svg class="cq-ring" viewBox="0 0 240 240">'
            f'<g transform="rotate(-90 120 {center_y})">'
            f'<circle cx="120" cy="{center_y}" r="{radius}" stroke="{TRACK}" '
            f'stroke-width="38" />'
            f'<circle class="cq-progress" cx="120" cy="{center_y}" r="{radius}" '
            f'stroke="{color}" stroke-width="38" stroke-linecap="round" '
            f'stroke-dasharray="{circumference:.2f}" '
            f'stroke-dashoffset="{offset:.2f}" /></g></svg>'
        )

    @staticmethod
    def _footer(text: str, color: str = FOOTER_GREY) -> str:
        if text == "--":
            return ""
        return (
            f'<div class="cq-footer" style="color:{color}">'
            f'<span class="cq-refresh">↻</span>{text}</div>'
        )

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        del ctx
        snapshot = self.snapshot(state)
        css = "\n".join(  # noqa: FLY002 - tuple keeps long CSS readable and lintable
            (
                "<style>",
                ".cq{position:absolute;inset:0;background:#000;color:#fff;overflow:hidden;"
                "font-family:'Nunito','DejaVu Sans',sans-serif;font-weight:900}",
                ".cq-ring{position:absolute;inset:0;width:100%;height:100%;overflow:visible}",
                ".cq-ring circle{fill:none}",
                ".cq-main{position:absolute;left:50%;top:43%;transform:translate(-50%,-50%);"
                "font-size:68px;line-height:.9;letter-spacing:-5px;white-space:nowrap;"
                "font-weight:900}",
                ".cq-footer{position:absolute;left:0;right:0;bottom:5px;text-align:center;"
                "font-size:23px;line-height:1;font-weight:900;white-space:nowrap}",
                ".cq-refresh{font-size:26px;margin-right:7px}",
                ".cq-empty .cq-main{top:50%;font-size:48px;letter-spacing:-3px}",
                ".cq-reset{position:absolute;inset:0;display:flex;flex-direction:column;"
                "align-items:center;justify-content:center;color:#39D353;font-size:58px;"
                "line-height:.92;letter-spacing:-3px;text-align:center}",
                ".cq-full-a{animation:cq-a 2s steps(1,end) infinite}",
                ".cq-full-b{animation:cq-b 2s steps(1,end) infinite}",
                "@keyframes cq-a{0%,49.99%{opacity:1}50%,100%{opacity:0}}",
                "@keyframes cq-b{0%,49.99%{opacity:0}50%,100%{opacity:1}}",
                "</style>",
            )
        )
        if snapshot.mode is QuotaMode.UNAVAILABLE:
            body = self._ring(100, EMPTY_RING, center_y=120, radius=90)
            body += '<div class="cq-main">--</div>'
            return css + f'<div class="cq cq-empty">{body}</div>'
        if snapshot.mode is QuotaMode.EMPTY:
            body = self._ring(100, EMPTY_RING, center_y=120, radius=90)
            body += f'<div class="cq-main">{snapshot.reset_text}</div>'
            return css + f'<div class="cq cq-empty">{body}</div>'
        assert snapshot.remaining_percent is not None
        ring = self._ring(snapshot.remaining_percent, snapshot.color)
        footer_color = (
            snapshot.color
            if snapshot.mode in {QuotaMode.WARNING, QuotaMode.CRITICAL}
            else FOOTER_GREY
        )
        face = ring
        face += (
            f'<div class="cq-main" style="color:{snapshot.color}">'
            f"{snapshot.remaining_percent}%</div>"
        )
        face += self._footer(snapshot.reset_text, footer_color)
        if snapshot.mode is QuotaMode.FULL:
            reset = '<div class="cq-reset"><div>CODEX</div><div>RESET!!</div></div>'
            return (
                css
                + f'<div class="cq"><div class="cq-full-a">{face}</div>'
                + f'<div class="cq-full-b">{reset}</div></div>'
            )
        return css + f'<div class="cq">{face}</div>'
