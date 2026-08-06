"""Climate widget for GeekMagic displays."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgba, mdi_span
from ._card import caption_max_chars, chip_html
from .base import Widget, WidgetConfig
from .helpers import truncate_text

if TYPE_CHECKING:
    from ..htmldoc import CellContext
    from .state import WidgetState


# HVAC action / mode → MDI icon (the "fire" / "snowflake" / "thermostat"
# state visual for the caption band).
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

# HVAC action / mode → theme palette *role*. The role name is both the
# CSS variable suffix (``var(--warning)``) and the ``Theme`` attribute
# (``theme.warning``), so the same mapping drives the markup tint and
# the concrete RGBA used for the cell wash (SVG/gradient color stops
# can't resolve ``var()``).
#
#   heating / preheating → warning / error   (warm)
#   cooling / drying     → info              (cool)
#   fan                  → success
#   idle                 → muted
#   off                  → error
HVAC_ACTION_ROLES: dict[str, str] = {
    "heating": "warning",
    "cooling": "info",
    "idle": "muted",
    "off": "error",
    "drying": "info",
    "fan": "success",
    "preheating": "error",
}

HVAC_MODE_ROLES: dict[str, str] = {
    "heat": "warning",
    "cool": "info",
    "heat_cool": "primary",
    "auto": "primary",
    "dry": "info",
    "fan_only": "success",
    "off": "error",
}

# Public CSS-variable views of the role maps — resolve to the active
# theme's palette at raster time so the heating flame is orange in
# watchOS, amber in retro, coral in candy, etc.
HVAC_ACTION_COLORS: dict[str, str] = {k: f"var(--{v})" for k, v in HVAC_ACTION_ROLES.items()}
HVAC_MODE_COLORS: dict[str, str] = {k: f"var(--{v})" for k, v in HVAC_MODE_ROLES.items()}

# Actions that earn the cell wash. Idle/off stay neutral — a red glow on
# a switched-off thermostat reads as an alarm, and a grey wash on idle is
# just noise.
_ACTIVE_ACTIONS = frozenset({"heating", "cooling", "drying", "fan", "preheating"})

# Smallest cell that gets the wash + hairline. Below this the cell is a
# grid tile and any backdrop treatment reads as dirt.
_WASH_MIN_PX = 170

# Chip metrics, mirroring CARD_CSS ``.chip``: font clamp(10, 11vmin, 16),
# padding 0.85em per side, icon 1em + 0.35em gap, ~0.58em per glyph.
_CHIP_GAP_PX = 5.0


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


def _hvac_role(hvac_action: str | None, hvac_mode: str) -> str:
    """Theme attribute name for the current HVAC state's tint."""
    if hvac_action and hvac_action != "idle":
        return HVAC_ACTION_ROLES.get(hvac_action, "primary")
    return HVAC_MODE_ROLES.get(hvac_mode, "primary")


def _chip_font_px(ctx: CellContext) -> float:
    """Resolved ``.chip`` font size for this cell (mirrors the clamp)."""
    return max(10.0, min(0.11 * min(ctx.width, ctx.height), 16.0))


def _chip_width_px(text: str, has_icon: bool, font_px: float) -> float:
    """Estimated rendered width of a chip pill, in pixels."""
    width = 1.7 * font_px + len(text) * 0.58 * font_px
    if has_icon:
        width += 1.35 * font_px
    return width


def _row_width_px(specs: list[tuple[str, str | None, str | None]], font_px: float) -> float:
    """Estimated width of a chip row including inter-chip gaps."""
    if not specs:
        return 0.0
    chips = sum(_chip_width_px(text, icon is not None, font_px) for text, icon, _ in specs)
    return chips + _CHIP_GAP_PX * (len(specs) - 1)


def _chip_rows(
    specs: list[tuple[str, str | None, str | None]], ctx: CellContext
) -> list[list[str]]:
    """Pack chip specs into rows that fit the cell width.

    Blitz has no ellipsis and does not clip text, so a chip strip that
    overflows simply bleeds past both cell edges. Measuring here keeps
    every pill inside the cell at any size.

    When everything fits, one row. When it doesn't, the leading (mode)
    chip takes a line of its own and the metric chips share the next —
    a 1+2 split reads as "status, then details", where the greedy 2+1
    split would orphan a single metric pill under a full row.
    """
    font_px = _chip_font_px(ctx)
    usable = ctx.width * 0.92
    if not specs or _row_width_px(specs, font_px) <= usable:
        return [[chip_html(t, icon=i, color=c) for t, i, c in specs]] if specs else []

    rows: list[list[tuple[str, str | None, str | None]]] = [[specs[0]]]
    for spec in specs[1:]:
        candidate = [*rows[-1], spec]
        if len(rows) > 1 and _row_width_px(candidate, font_px) <= usable:
            rows[-1] = candidate
        else:
            rows.append([spec])
    return [[chip_html(t, icon=i, color=c) for t, i, c in row] for row in rows]


# Widget-scoped CSS. Injected with the fragment (Blitz honours <style>
# in the body, including media queries, and the cell document only ever
# contains this one widget).
_CLIMATE_CSS = """
<style>
.clim-hero { display: flex; align-items: baseline; justify-content: center;
             gap: 0.04em; max-width: 100%; }
/* The chip stack owns its own breakpoint rather than using .hide-small:
   a thermostat tile without its state is worth much less than one with
   it, so chips survive down to 100px (2x2 grid) where the kit would
   drop them at 130px. Python trims the chip SET to match. */
.clim-stack { display: none; flex-direction: column; align-items: center;
              gap: 4px; width: 100%; }
@media (min-width: 100px) and (min-height: 100px) { .clim-stack { display: flex; } }
/* Wide strip cells are too short for bands but far too wide for a lone
   hero, so they lay the same content out horizontally instead. */
.clim-strip { display: flex; align-items: center; gap: 0.18em; }
</style>
"""


def _climate_placeholder() -> str:
    """Placeholder fragment when no climate data is available."""
    icon = mdi_span("thermostat", "icon i-md", "color: var(--text-secondary)")
    return f'<div class="cell">{icon}<div class="t-label hide-short">NO CLIMATE DATA</div></div>'


class ClimateWidget(Widget):
    """Widget that displays climate/thermostat information.

    watchOS-style thermostat card:
      caption = state-tinted HVAC icon + room name (one line)
      hero    = current temperature, big numerals + smaller degree unit
      chips   = [mode chip (state-tinted), target chip, humidity chip],
                wrapped to a second row when they don't fit the width
      wash    = in fullscreen cells, a soft radial tint of the running
                action (warm when heating, cool when cooling)
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

    # ------------------------------------------------------------------
    # Fragment builders
    # ------------------------------------------------------------------

    @staticmethod
    def _wash_style(ctx: CellContext, hvac_action: str | None, role: str) -> str:
        """Inline style for the cell: rounded corners + optional action wash.

        A radial tint of the running action, peaking around 10% alpha at
        the top of the cell and gone by two thirds down — enough to read
        as warmth/coolness at a glance without competing with the hero.
        """
        style = "border-radius: var(--radius);"
        theme = ctx.theme
        if theme is None or hvac_action not in _ACTIVE_ACTIONS:
            return style
        if min(ctx.width, ctx.height) < _WASH_MIN_PX:
            return style
        color = getattr(theme, role, None) or getattr(theme, "primary")
        return (
            f"{style} background: radial-gradient(120% 78% at 50% 4%, "
            f"{css_rgba(color, 0.13)}, {css_rgba(color, 0.0)} 70%);"
        )

    @staticmethod
    def _caption_html(ctx: CellContext, label: str, icon: str, tint: str) -> str:
        """Tinted state icon + room name, truncated to the cell width.

        Uses a wider per-glyph estimate than :func:`caption_max_chars`
        because the caption shares its line with the state icon and
        because the widest theme combination (retro: DejaVu Sans at
        0.2em tracking) needs ~0.8em per character, not 0.68em.
        """
        label_px = max(10.0, min(0.10 * min(ctx.width, ctx.height), 0.075 * ctx.width, 15.0))
        # Narrow cells spend ~18px of ~105px usable on the state icon —
        # two whole characters of the room name. The chip strip already
        # carries the tint there, so the caption keeps the full name.
        with_icon = ctx.width >= 150
        icon_px = max(11.0, min(0.12 * min(ctx.width, ctx.height), 24.0)) if with_icon else 0.0
        budget = ctx.width * 0.90 - icon_px - (0.45 * label_px if with_icon else 0.0)
        text = truncate_text(label.upper(), max(4, int(budget / (label_px * 0.80))))
        icon_html = mdi_span(icon, "icon i-sm", f"color: {tint}") if with_icon else ""
        return f'<div class="t-label caption-row hide-short">{icon_html}{escape(text)}</div>'

    @staticmethod
    def _hero_html(value: str, unit: str) -> str:
        """Big numerals with the degree unit set smaller and secondary."""
        unit_html = f'<span class="t-unit">{escape(unit)}</span>' if unit and value != "--" else ""
        return f'<div class="clim-hero"><span class="t-hero">{escape(value)}</span>{unit_html}</div>'

    def _chip_specs(
        self, entity: Any, hvac_action: str | None, hvac_mode: str
    ) -> list[tuple[str, str | None, str | None]]:
        """(text, icon, color) for each supporting pill, in priority order."""
        specs: list[tuple[str, str | None, str | None]] = []
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
                specs.append((mode_key.replace("_", " ").upper(), None, mode_color))
        if self.show_target and entity.get("temperature") is not None:
            specs.append((_format_temp(entity.get("temperature")), "target", None))
        if self.show_humidity and entity.get("humidity") is not None:
            try:
                humidity_val = int(float(entity.get("humidity")))
            except (ValueError, TypeError):
                pass
            else:
                specs.append((f"{humidity_val}%", "water-percent", "var(--info)"))
        return specs

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the climate widget."""
        entity = state.entity
        if entity is None:
            return _climate_placeholder()

        hvac_mode = entity.state
        hvac_action = entity.get("hvac_action")
        icon_name, icon_color = _hvac_visual(hvac_action, hvac_mode)
        role = _hvac_role(hvac_action, hvac_mode)

        unit = entity.get("temperature_unit") or "°C"
        value = _format_temp(entity.get("current_temperature"), "")

        bands = [
            self._caption_html(ctx, self.label_for(entity), icon_name, icon_color),
            self._hero_html(value, unit),
        ]

        # Width decides how the pills pack; height decides how many rows
        # the cell can afford. A 2x2 tile keeps only the running state,
        # a split-v column stacks all three, a wide strip fits one row.
        max_rows = 1 if ctx.height < 150 else 3
        rows = _chip_rows(self._chip_specs(entity, hvac_action, hvac_mode), ctx)[:max_rows]
        if rows:
            strip = "".join(f'<div class="chips">{"".join(row)}</div>' for row in rows)
            bands.append(f'<div class="clim-stack">{strip}</div>')

        cell_style = self._wash_style(ctx, hvac_action, role)
        return f'{_CLIMATE_CSS}<div class="cell" style="{cell_style}">{"".join(bands)}</div>'
