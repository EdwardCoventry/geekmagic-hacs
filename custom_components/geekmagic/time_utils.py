"""Timezone helpers shared by production and preview rendering."""

from __future__ import annotations

from datetime import UTC, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_hass_timezone(config) -> tzinfo:
    """Resolve Home Assistant's configured timezone across HA versions."""
    configured = getattr(config, "time_zone_obj", None)
    if configured is not None:
        return configured
    name = getattr(config, "time_zone", None)
    if name:
        try:
            return ZoneInfo(str(name))
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return UTC
