"""Climate widget for GeekMagic displays."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import mdi_span
from ._card import card_html, chip_html
from .base import Widget, WidgetConfig

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


# HVAC action / mode → MDI icon (the "fire" / "snowflake" / "thermostat"
# state visual for the feature band).
HVAC_ACTION_ICONS = {
    "heating": "fire",
    "cooling": "snowflake",
    "idle": "thermostat",
    "off": "power-standby",
    "drying": "water-percent",
    "fan": "fan",
    "preheating": "fire",
}

HVAC_MODE_ICONS = {
    "heat": "fire",
    "cool": "snowflake",
    "heat_cool": "sun-snowflake-variant",
    "auto": "thermostat-auto",
    "dry": "water-percent",
    "fan_only": "fan",
    "off": "power-standby",
}

# HVAC action / mode → theme palette CSS variable. Resolves to the active
# theme's warning / info / muted at raster time so the heating flame is
# orange in watchOS, amber in retro, coral in candy, etc. — no hardcoded
# RGB leaks through to widget code.
HVAC_ACTION_COLORS: dict[str, str] = {
    "heating": "var(--warning)",
    "cooling": "var(--info)",
    "idle": "var(--muted)",
    "off": "var(--error)",
    "drying": "var(--info)",
    "fan": "var(--success)",
    "preheating": "var(--error)",
}

HVAC_MODE_COLORS: dict[str, str] = {
    "heat": "var(--warning)",
    "cool": "var(--info)",
    "heat_cool": "var(--primary)",
    "auto": "var(--primary)",
    "dry": "var(--info)",
    "fan_only": "var(--success)",
    "off": "var(--error)",
}


def _format_temp(value: float | str | None, unit: str = "°") -> str:
    """Format temperature value for display."""
    if value is None:
        return "--"
    try:
        num = float(value)
    except (ValueError, TypeError):
        return "--"
    if num == int(num):
        return f"{int(num)}{unit}"
    return f"{num:.1f}{unit}"


def _hvac_visual(hvac_action: str | None, hvac_mode: str) -> tuple[str, str]:
    """Pick the HVAC icon + theme-role CSS color for the current state.

    ``hvac_action`` is the live action ("heating", "cooling") and wins
    when present and not ``"idle"``. ``hvac_mode`` is the configured
    mode and is the fallback (used when the unit is reporting idle or
    didn't expose ``hvac_action``).
    """
    if hvac_action and hvac_action != "idle":
        return (
            HVAC_ACTION_ICONS.get(hvac_action, "thermostat"),
            HVAC_ACTION_COLORS.get(hvac_action, "var(--primary)"),
        )
    return (
        HVAC_MODE_ICONS.get(hvac_mode, "thermostat"),
        HVAC_MODE_COLORS.get(hvac_mode, "var(--primary)"),
    )


def _climate_placeholder() -> str:
    """Placeholder fragment when no climate data is available."""
    icon = mdi_span("thermostat", "icon i-md", "color: var(--text-secondary)")
    return f'<div class="cell">{icon}<div class="t-label hide-short">NO CLIMATE DATA</div></div>'


class ClimateWidget(Widget):
    """Widget that displays climate/thermostat information.

    Three-band card:
      caption  = widget label / entity name
      icon     = state-tinted HVAC icon (fire / snowflake / fan / ...)
      hero     = current temperature ("21.5°C")
      chips    = [mode chip (state-tinted), target chip, humidity chip]
    """

    WIDGET_TYPE: ClassVar[str] = "climate"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Climate",
        "needs_entity": True,
        "entity_domains": ["climate"],
        "options": [
            {"key": "show_target", "type": "boolean", "label": "Show Target Temp", "default": True},
            {"key": "show_humidity", "type": "boolean", "label": "Show Humidity", "default": True},
            {"key": "show_mode", "type": "boolean", "label": "Show HVAC Mode", "default": True},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the climate widget."""
        super().__init__(config)
        self.show_target = config.options.get("show_target", True)
        self.show_humidity = config.options.get("show_humidity", True)
        self.show_mode = config.options.get("show_mode", True)

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the climate widget."""
        entity = state.entity
        if entity is None:
            return _climate_placeholder()

        hvac_mode = entity.state
        hvac_action = entity.get("hvac_action")
        icon_name, icon_color = _hvac_visual(hvac_action, hvac_mode)

        unit = entity.get("temperature_unit") or "°C"
        hero = _format_temp(entity.get("current_temperature"), unit)

        # Supporting chips: HVAC mode/action + target temp + humidity.
        chips: list[str] = []
        if self.show_mode:
            mode_key = hvac_action or hvac_mode
            if mode_key:
                # Mode chip tint keys on the *displayed* state, so "IDLE"
                # is muted even when the configured mode would tint the
                # icon (mode-chip text tint is an allowed exception).
                mode_color = (
                    HVAC_ACTION_COLORS.get(mode_key)
                    or HVAC_MODE_COLORS.get(mode_key)
                    or "var(--primary)"
                )
                chips.append(chip_html(mode_key.replace("_", " ").upper(), color=mode_color))
        if self.show_target and entity.get("temperature") is not None:
            chips.append(chip_html(_format_temp(entity.get("temperature")), icon="target"))
        if self.show_humidity and entity.get("humidity") is not None:
            try:
                humidity_val = int(float(entity.get("humidity")))
            except (ValueError, TypeError):
                pass
            else:
                chips.append(
                    chip_html(f"{humidity_val}%", icon="water-percent", color="var(--info)")
                )

        return card_html(
            caption=self.label_for(entity),
            icon=icon_name,
            icon_color=icon_color,
            icon_role="feature",
            hero=hero,
            chips=chips or None,
        )
