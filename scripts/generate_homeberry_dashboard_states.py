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
TEMP = "sensor.temp_temperature"
WEATHER = "weather.forecast_home"
SCENE = "sensor.homeberry_runtime_active_scene"


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
                    "temperature_entity_id": TEMP,
                    "weather_entity_id": WEATHER,
                    "scene_entity_id": SCENE,
                },
            )
        ),
    )
    return layout


def _state(quota: str, *, scene: str = "Movie") -> WidgetState:
    return WidgetState(
        entity=EntityState(
            CODEX,
            quota,
            {"secondary_reset_at": (NOW + timedelta(days=3, hours=5)).timestamp()},
        ),
        entities={
            TEMP: EntityState(TEMP, "25.6", {"unit_of_measurement": "°C"}),
            WEATHER: EntityState(WEATHER, "partlycloudy", {"temperature": 20}),
            SCENE: EntityState(SCENE, scene, {"active_scene_id": scene.lower()}),
        },
        now=NOW,
    )


def _still(quota: str) -> Image.Image:
    renderer = Renderer()
    canvas, draw = renderer.create_canvas()
    _layout().render(renderer, draw, {0: _state(quota)})
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
    manifest = {
        "display_size": [240, 240],
        "normal_quota": 68,
        "full_animation_frame_times": [0.0, 1.0],
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
