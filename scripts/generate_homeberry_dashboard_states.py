#!/usr/bin/env python3
"""Generate production-rendered Homeberry dashboard preview artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.geekmagic.htmldoc import HAS_BLITZ, HAS_FRAMES
from custom_components.geekmagic.layouts.fullscreen import FullscreenLayout
from custom_components.geekmagic.renderer import Renderer
from custom_components.geekmagic.widgets import HomeberryDashboardWidget, WidgetConfig
from custom_components.geekmagic.widgets.state import EntityState, WidgetState

NOW = datetime(2026, 8, 11, 9, 42, tzinfo=UTC)
CODEX = "sensor.codex_usage_codex_weekly_remaining"
WEATHER = "weather.forecast_home"
SCENE = "sensor.homeberry_runtime_active_scene"
INDOOR = "sensor.homeberry_runtime_indoor_temperature"
OUTDOOR = "sensor.homeberry_runtime_outdoor_temperature"
HEALTH = "sensor.homeberry_runtime_device_health"
CONNECTION = "sensor.homeberry_runtime_connection"
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
THERMAL_STATES = {
    "window-open-until": {
        "kind": "window_open",
        "icon": "window-open-variant",
        "until_at": "2026-08-11T14:00:00+00:00",
        "all_day": False,
        "target_temperature_c": 21,
    },
    "window-open-all-day": {
        "kind": "window_open",
        "icon": "window-open-variant",
        "until_at": "2026-08-11T22:00:00+00:00",
        "all_day": True,
        "target_temperature_c": 21,
    },
    "window-keep-open": {
        "kind": "window_keep_open",
        "icon": "window-open-variant",
        "until_at": "2026-08-11T14:00:00+00:00",
        "all_day": False,
        "target_temperature_c": 21,
    },
    "window-closed": {
        "kind": "window_closed",
        "icon": "window-closed-variant",
        "until_at": "2026-08-11T20:00:00+00:00",
        "all_day": False,
        "target_temperature_c": 21,
    },
    "heating": {
        "kind": "heating",
        "icon": "radiator",
        "until_at": None,
        "all_day": False,
        "target_temperature_c": 21,
    },
    "holding": {
        "kind": "holding",
        "icon": "thermostat",
        "until_at": None,
        "all_day": False,
        "target_temperature_c": 21,
    },
    "heating-off": {
        "kind": "heating_off",
        "icon": "radiator-off",
        "until_at": "2026-08-12T02:30:00+00:00",
        "all_day": False,
        "target_temperature_c": 21,
    },
    "unavailable": {
        "kind": "unavailable",
        "icon": "thermometer-alert",
        "until_at": None,
        "all_day": False,
        "target_temperature_c": None,
    },
}
QUOTA_ALIGNMENT_STATES = ("1", "9", "10", "68", "99", "100")
TEMPERATURE_COMPARISON_STATES = {
    "out-hotter": (27.6, 22.4),
    "in-hotter": (18.2, 23.1),
    "equal-displayed": (22.4, 22.3),
}
HEALTH_STATES = {
    "none": ({"battery": 0, "connectivity": 0, "other": 0}, "healthy"),
    "battery": ({"battery": 1, "connectivity": 0, "other": 0}, "warning"),
    "connectivity": ({"battery": 0, "connectivity": 2, "other": 0}, "warning"),
    "other": ({"battery": 0, "connectivity": 0, "other": 1}, "warning"),
    "mixed-critical": ({"battery": 1, "connectivity": 2, "other": 1}, "critical"),
}
HEALTH_ISSUES = {
    "battery": ("Motion", "Motion BATTERY", "Battery low"),
    "connectivity": ("Heater", "Heater OFFLINE", "Offline"),
    "other": ("Temp", "Temp STALE", "Data age is unknown"),
}
SPACING_BAND_NAMES = (
    "time_weather",
    "date_outdoor",
    "guidance_indoor",
    "scenes",
    "codex_stats",
    "codex_bar",
)
SPACING_COLORS = (
    "#FF4D6D",
    "#00D4FF",
    "#FFD166",
    "#B86BFF",
    "#39D353",
    "#FF8C42",
)
SPACING_TARGET_PX = 6


def analyze_visual_spacing(image: Image.Image) -> dict[str, object]:
    """Measure actual visible pixel bands rather than CSS line boxes."""
    rgb = image.convert("RGB")
    occupied_rows = [
        any(max(rgb.getpixel((x, y))) > 12 for x in range(rgb.width)) for y in range(rgb.height)
    ]
    ranges: list[tuple[int, int]] = []
    start = None
    for y, occupied in enumerate([*occupied_rows, False]):
        if occupied and start is None:
            start = y
        elif not occupied and start is not None:
            ranges.append((start, y - 1))
            start = None
    if len(ranges) != len(SPACING_BAND_NAMES):
        raise RuntimeError(
            f"Expected {len(SPACING_BAND_NAMES)} visual bands, found {len(ranges)}: {ranges}"
        )

    bands = []
    for name, color, (top, bottom) in zip(SPACING_BAND_NAMES, SPACING_COLORS, ranges, strict=True):
        occupied_pixels = [
            (x, y)
            for y in range(top, bottom + 1)
            for x in range(rgb.width)
            if max(rgb.getpixel((x, y))) > 12
        ]
        bands.append(
            {
                "name": name,
                "color": color,
                "left": min(x for x, _ in occupied_pixels),
                "top": top,
                "right": max(x for x, _ in occupied_pixels),
                "bottom": bottom,
                "height": bottom - top + 1,
            }
        )

    gaps = []
    recommendations = []
    for first, second in pairwise(bands):
        pixels = int(second["top"]) - int(first["bottom"]) - 1
        delta = SPACING_TARGET_PX - pixels
        gap = {
            "after": first["name"],
            "before": second["name"],
            "pixels": pixels,
            "target": SPACING_TARGET_PX,
            "delta": delta,
        }
        gaps.append(gap)
        if delta:
            direction = "increase" if delta > 0 else "decrease"
            recommendations.append(
                f"{first['name']} -> {second['name']}: {pixels}px; {direction} by {abs(delta)}px"
            )
    return {
        "target_gap_px": SPACING_TARGET_PX,
        "passed": not recommendations,
        "bands": bands,
        "gaps": gaps,
        "recommendations": recommendations,
    }


def spacing_diagnostic_image(image: Image.Image, report: dict[str, object]) -> Image.Image:
    """Draw measured visual bounds and a compact gap report."""
    source = image.convert("RGB")
    diagnostic = Image.new("RGB", (480, 240), "black")
    diagnostic.paste(source, (0, 0))
    draw = ImageDraw.Draw(diagnostic)
    for band in report["bands"]:
        draw.rectangle(
            (
                int(band["left"]),
                int(band["top"]),
                int(band["right"]),
                int(band["bottom"]),
            ),
            outline=str(band["color"]),
            width=1,
        )
    draw.text((250, 8), "VISUAL SPACING", fill="white")
    y = 25
    for band in report["bands"]:
        draw.rectangle((250, y + 2, 257, y + 9), fill=str(band["color"]))
        draw.text(
            (262, y),
            f"{band['name']} {band['top']}..{band['bottom']}",
            fill="white",
        )
        y += 16
    y += 3
    for gap in report["gaps"]:
        color = "#39D353" if gap["pixels"] == gap["target"] else "#FF6B6B"
        draw.text(
            (250, y),
            f"gap {gap['after']} -> {gap['before']}: {gap['pixels']}px",
            fill=color,
        )
        y += 14
    draw.text(
        (250, 225),
        f"TARGET {report['target_gap_px']}px  {'PASS' if report['passed'] else 'FAIL'}",
        fill="#39D353" if report["passed"] else "#FF6B6B",
    )
    return diagnostic


def _layout() -> FullscreenLayout:
    layout = FullscreenLayout()
    layout.set_widget(
        0,
        HomeberryDashboardWidget(
            WidgetConfig(
                widget_type="homeberry_dashboard",
                slot=0,
                entity_id=CODEX,
                options={
                    "weather_entity_id": WEATHER,
                    "scene_entity_id": SCENE,
                    "indoor_temperature_entity_id": INDOOR,
                    "outdoor_temperature_entity_id": OUTDOOR,
                    "health_entity_id": HEALTH,
                    "connection_entity_id": CONNECTION,
                },
            )
        ),
    )
    return layout


def _state(
    quota: str,
    *,
    scene: str = "Movie",
    thermal_guidance: dict[str, object] | None = None,
    outdoor_temperature: float = 27.6,
    indoor_temperature: float = 22.4,
    outdoor_fallback: bool = False,
    unavailable_temperatures: bool = False,
    health_counts: dict[str, int] | None = None,
    health_severity: str = "healthy",
    runtime_connection: str = "online",
) -> WidgetState:
    resolved_health_counts = health_counts or {
        "battery": 0,
        "connectivity": 0,
        "other": 0,
    }
    top_issues = [
        {
            "asset_id": f"device.{display_name.lower()}",
            "display_name": display_name,
            "category": category,
            "severity": health_severity if health_severity == "critical" else "warning",
            "summary": f"{display_name}: {summary}",
            "short_label": short_label,
        }
        for category, count in resolved_health_counts.items()
        if count > 0
        for display_name, short_label, summary in (HEALTH_ISSUES[category],)
    ]
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
                scene,
                {
                    "active_scene_id": scene.lower(),
                    "scene_chips": SCENE_CHIPS,
                    "thermal_guidance": thermal_guidance or THERMAL_STATES["window-open-until"],
                },
            ),
            **(
                {}
                if unavailable_temperatures
                else {
                    INDOOR: EntityState(
                        INDOOR, str(indoor_temperature), {"quality": "measured", "fallback": False}
                    ),
                    OUTDOOR: EntityState(
                        OUTDOOR,
                        str(outdoor_temperature),
                        {
                            "quality": "estimated" if outdoor_fallback else "measured",
                            "fallback": outdoor_fallback,
                        },
                    ),
                }
            ),
            HEALTH: EntityState(
                HEALTH,
                str(sum((health_counts or {}).values())),
                {
                    "category_counts": resolved_health_counts,
                    "overall_severity": health_severity,
                    "top_issues": top_issues,
                    "category_severity": {
                        category: (
                            "critical"
                            if health_severity == "critical" and category == "battery" and count
                            else "warning"
                            if count
                            else "healthy"
                        )
                        for category, count in (resolved_health_counts).items()
                    },
                },
            ),
            CONNECTION: EntityState(CONNECTION, runtime_connection, {}),
        },
        now=NOW,
    )


def _still(
    quota: str,
    *,
    thermal_guidance: dict[str, object] | None = None,
    outdoor_temperature: float = 27.6,
    indoor_temperature: float = 22.4,
    outdoor_fallback: bool = False,
    unavailable_temperatures: bool = False,
    health_counts: dict[str, int] | None = None,
    health_severity: str = "healthy",
    runtime_connection: str = "online",
) -> Image.Image:
    renderer = Renderer()
    canvas, draw = renderer.create_canvas()
    _layout().render(
        renderer,
        draw,
        {
            0: _state(
                quota,
                thermal_guidance=thermal_guidance,
                outdoor_temperature=outdoor_temperature,
                indoor_temperature=indoor_temperature,
                outdoor_fallback=outdoor_fallback,
                unavailable_temperatures=unavailable_temperatures,
                health_counts=health_counts,
                health_severity=health_severity,
                runtime_connection=runtime_connection,
            )
        },
    )
    return renderer.finalize(canvas)


def _full_frames() -> tuple[list[Image.Image], bytes]:
    if not (HAS_BLITZ and HAS_FRAMES):
        raise RuntimeError("blitz-py frame rendering is required")
    renderer = Renderer()
    frames = _layout().render_animation(renderer, {0: _state("100")}, [0.0, 1.0])
    if frames is None or len(frames) != 2:
        raise RuntimeError("the renderer did not return both reset frames")
    return [renderer.finalize(frame) for frame in frames], renderer.to_gif(frames, fps=1)


def generate(output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    normal = _still("68")
    normal.save(output / "homeberry-dashboard-normal.png")
    spacing_report = analyze_visual_spacing(normal)
    spacing_diagnostic_image(normal, spacing_report).save(
        output / "homeberry-dashboard-spacing-diagnostic.png"
    )
    (output / "homeberry-dashboard-spacing-report.json").write_text(
        json.dumps(spacing_report, indent=2), encoding="utf-8"
    )
    frames, gif = _full_frames()
    frames[0].save(output / "homeberry-dashboard-full-frame-1.png")
    frames[1].save(output / "homeberry-dashboard-full-frame-2.png")
    (output / "homeberry-dashboard-full-reset.gif").write_bytes(gif)

    sheet = Image.new("RGB", (720, 240), "black")
    sheet.paste(normal, (0, 0))
    sheet.paste(frames[0], (240, 0))
    sheet.paste(frames[1], (480, 0))
    sheet.save(output / "homeberry-dashboard-storyboard.png")

    thermal_images = []
    thermal_spacing_reports = {}
    for name, guidance in THERMAL_STATES.items():
        rendered = _still("68", thermal_guidance=guidance)
        rendered.save(output / f"homeberry-dashboard-thermal-{name}.png")
        thermal_images.append(rendered)
        thermal_spacing_reports[name] = analyze_visual_spacing(rendered)
    thermal_sheet = Image.new("RGB", (960, 480), "black")
    for index, rendered in enumerate(thermal_images):
        thermal_sheet.paste(rendered, ((index % 4) * 240, (index // 4) * 240))
    thermal_sheet.save(output / "homeberry-dashboard-thermal-storyboard.png")

    quota_images = [_still(quota) for quota in QUOTA_ALIGNMENT_STATES]
    quota_sheet = Image.new("RGB", (720, 480), "black")
    for index, rendered in enumerate(quota_images):
        quota_sheet.paste(rendered, ((index % 3) * 240, (index // 3) * 240))
    quota_sheet.save(output / "homeberry-dashboard-quota-alignment-storyboard.png")

    temperature_images = []
    temperature_spacing_reports = {}
    for name, (outdoor, indoor) in TEMPERATURE_COMPARISON_STATES.items():
        rendered = _still("68", outdoor_temperature=outdoor, indoor_temperature=indoor)
        rendered.save(output / f"homeberry-dashboard-temperature-{name}.png")
        temperature_images.append(rendered)
        temperature_spacing_reports[name] = analyze_visual_spacing(rendered)
    temperature_sheet = Image.new("RGB", (720, 240), "black")
    for index, rendered in enumerate(temperature_images):
        temperature_sheet.paste(rendered, (index * 240, 0))
    temperature_sheet.save(output / "homeberry-dashboard-temperature-storyboard.png")

    provenance_images = [
        _still("68", outdoor_fallback=True),
        _still("68", unavailable_temperatures=True),
    ]
    provenance_sheet = Image.new("RGB", (480, 240), "black")
    for index, rendered in enumerate(provenance_images):
        rendered.save(output / f"homeberry-dashboard-provenance-{index + 1}.png")
        provenance_sheet.paste(rendered, (index * 240, 0))
    provenance_sheet.save(output / "homeberry-dashboard-provenance-storyboard.png")

    health_images = []
    for name, (counts, severity) in HEALTH_STATES.items():
        rendered = _still("68", health_counts=counts, health_severity=severity)
        rendered.save(output / f"homeberry-dashboard-health-{name}.png")
        health_images.append(rendered)
    health_sheet = Image.new("RGB", (1200, 240), "black")
    for index, rendered in enumerate(health_images):
        health_sheet.paste(rendered, (index * 240, 0))
    health_sheet.save(output / "homeberry-dashboard-health-storyboard.png")
    offline = _still("68", unavailable_temperatures=True, runtime_connection="offline")
    offline.save(output / "homeberry-dashboard-connection-offline.png")
    manifest = {
        "display_size": [240, 240],
        "normal_quota": 68,
        "full_animation_frame_times": [0.0, 1.0],
        "thermal_storyboard_order": list(THERMAL_STATES),
        "quota_alignment_storyboard_order": list(QUOTA_ALIGNMENT_STATES),
        "temperature_storyboard_order": list(TEMPERATURE_COMPARISON_STATES),
        "health_storyboard_order": list(HEALTH_STATES),
        "visual_spacing": spacing_report,
        "thermal_visual_spacing": thermal_spacing_reports,
        "temperature_visual_spacing": temperature_spacing_reports,
        "files": sorted(path.name for path in output.iterdir() if path.is_file()),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/homeberry-dashboard-states"),
    )
    args = parser.parse_args()
    result = generate(args.output.resolve())
    print(json.dumps({"output": str(args.output.resolve()), **result}, indent=2))


if __name__ == "__main__":
    main()
