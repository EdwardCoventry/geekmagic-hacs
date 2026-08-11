#!/usr/bin/env python3
"""Generate production-rendered Homeberry dashboard preview artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image

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
        "until_at": None,
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
) -> WidgetState:
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
                    "indoor_temperature_c": 22.4,
                    "outdoor_temperature_c": 27.6,
                    "thermal_guidance": thermal_guidance
                    or THERMAL_STATES["window-open-until"],
                },
            ),
        },
        now=NOW,
    )


def _still(
    quota: str,
    *,
    thermal_guidance: dict[str, object] | None = None,
) -> Image.Image:
    renderer = Renderer()
    canvas, draw = renderer.create_canvas()
    _layout().render(
        renderer,
        draw,
        {0: _state(quota, thermal_guidance=thermal_guidance)},
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
    for name, guidance in THERMAL_STATES.items():
        rendered = _still("68", thermal_guidance=guidance)
        rendered.save(output / f"homeberry-dashboard-thermal-{name}.png")
        thermal_images.append(rendered)
    thermal_sheet = Image.new("RGB", (960, 480), "black")
    for index, rendered in enumerate(thermal_images):
        thermal_sheet.paste(rendered, ((index % 4) * 240, (index // 4) * 240))
    thermal_sheet.save(output / "homeberry-dashboard-thermal-storyboard.png")

    quota_images = [_still(quota) for quota in QUOTA_ALIGNMENT_STATES]
    quota_sheet = Image.new("RGB", (720, 480), "black")
    for index, rendered in enumerate(quota_images):
        quota_sheet.paste(rendered, ((index % 3) * 240, (index // 3) * 240))
    quota_sheet.save(output / "homeberry-dashboard-quota-alignment-storyboard.png")
    manifest = {
        "display_size": [240, 240],
        "normal_quota": 68,
        "full_animation_frame_times": [0.0, 1.0],
        "thermal_storyboard_order": list(THERMAL_STATES),
        "quota_alignment_storyboard_order": list(QUOTA_ALIGNMENT_STATES),
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
