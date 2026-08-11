#!/usr/bin/env python3
"""Render the complete visual state set for the Codex quota widget.

Run from the repository root:

    uv run python scripts/generate_codex_quota_states.py

Use ``--output`` to choose another artifact directory. The generator uses the
same widget, fullscreen layout, Blitz renderer, and GIF encoder as the Home
Assistant integration, so the resulting 240x240 images are production renders.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent))

from custom_components.geekmagic.htmldoc import HAS_BLITZ, HAS_FRAMES
from custom_components.geekmagic.layouts.fullscreen import FullscreenLayout
from custom_components.geekmagic.renderer import Renderer
from custom_components.geekmagic.widgets.base import WidgetConfig
from custom_components.geekmagic.widgets.codex_quota import CodexQuotaWidget
from custom_components.geekmagic.widgets.state import EntityState, WidgetState

ENTITY_ID = "sensor.codex_usage_codex_weekly_remaining"
DEFAULT_NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
DEFAULT_RESET_SECONDS = 3 * 86_400 + 5 * 3_600
FRAME_TIMES = (0.0, 1.0)


@dataclass(frozen=True)
class StateCase:
    """One representative semantic quota state."""

    slug: str
    label: str
    value: str


STATE_CASES = (
    StateCase("unknown", "Unknown / unavailable", "unavailable"),
    StateCase("empty", "Empty (0%)", "0"),
    StateCase("critical-red", "Critical (1-5%)", "3"),
    StateCase("warning-amber", "Warning (6-20%)", "12"),
    StateCase("healthy-green", "Healthy (21-99%)", "50"),
    StateCase("full", "Full reset (100%)", "100"),
)


def _widget() -> CodexQuotaWidget:
    return CodexQuotaWidget(
        WidgetConfig(widget_type="codex_quota", slot=0, entity_id=ENTITY_ID)
    )


def _state(value: str, now: datetime, reset_seconds: int) -> WidgetState:
    entity = EntityState(
        ENTITY_ID,
        value,
        {"secondary_reset_at": (now + timedelta(seconds=reset_seconds)).timestamp()},
    )
    return WidgetState(entity=entity, now=now)


def _layout() -> FullscreenLayout:
    layout = FullscreenLayout()
    layout.set_widget(0, _widget())
    return layout


def render_still(value: str, now: datetime, reset_seconds: int) -> Image.Image:
    """Render one final-resolution production still."""
    renderer = Renderer()
    layout = _layout()
    canvas, draw = renderer.create_canvas()
    layout.render(renderer, draw, {0: _state(value, now, reset_seconds)})
    return renderer.finalize(canvas)


def render_full_frames(now: datetime, reset_seconds: int) -> list[Image.Image]:
    """Render both distinct one-second faces of the 100% animation."""
    if not (HAS_BLITZ and HAS_FRAMES):
        raise RuntimeError("blitz-py frame rendering is required for the 100% animation")
    renderer = Renderer()
    frames = _layout().render_animation(
        renderer,
        {0: _state("100", now, reset_seconds)},
        list(FRAME_TIMES),
    )
    if frames is None or len(frames) != len(FRAME_TIMES):
        raise RuntimeError("the production renderer did not return both 100% frames")
    return [renderer.finalize(frame) for frame in frames]


def _save_gif(frames: list[Image.Image], path: Path) -> None:
    """Save the two-face loop at one frame per second."""
    renderer = Renderer()
    supersampled = [
        frame.resize(
            (renderer.width * renderer.scale, renderer.height * renderer.scale),
            Image.Resampling.NEAREST,
        )
        for frame in frames
    ]
    path.write_bytes(renderer.to_gif(supersampled, fps=1))


def _contact_sheet(panels: list[tuple[str, Image.Image]], path: Path) -> None:
    """Create a labeled overview without altering individual device renders."""
    columns = 3
    tile_width = 260
    label_height = 38
    tile_height = 240 + label_height
    rows = (len(panels) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), "#17191d")
    draw = ImageDraw.Draw(sheet)
    font_path = (
        Path(__file__).parent.parent
        / "custom_components"
        / "geekmagic"
        / "fonts"
        / "Nunito-ExtraBold.ttf"
    )
    font = ImageFont.truetype(str(font_path), 17)
    for index, (label, image) in enumerate(panels):
        column = index % columns
        row = index // columns
        x = column * tile_width
        y = row * tile_height
        sheet.paste(image, (x + 10, y))
        text_box = draw.textbbox((0, 0), label, font=font)
        text_width = text_box[2] - text_box[0]
        draw.text(
            (x + (tile_width - text_width) / 2, y + 247),
            label,
            fill="#f2f3f5",
            font=font,
        )
    sheet.save(path)


def generate(output: Path, now: datetime, reset_seconds: int) -> dict[str, object]:
    """Generate individual screenshots, animation artifacts, and manifest."""
    output.mkdir(parents=True, exist_ok=True)
    panels: list[tuple[str, Image.Image]] = []
    files: list[str] = []

    for case in STATE_CASES:
        if case.slug == "full":
            continue
        image = render_still(case.value, now, reset_seconds)
        filename = f"codex-quota-{case.slug}.png"
        image.save(output / filename)
        files.append(filename)
        panels.append((case.label, image))

    full_frames = render_full_frames(now, reset_seconds)
    frame_labels = ("Full: 100% face", "Full: RESET!! face")
    for index, (label, image) in enumerate(zip(frame_labels, full_frames, strict=True), start=1):
        filename = f"codex-quota-full-frame-{index}.png"
        image.save(output / filename)
        files.append(filename)
        panels.append((label, image))

    gif_name = "codex-quota-full-reset.gif"
    _save_gif(full_frames, output / gif_name)
    files.append(gif_name)

    sheet_name = "codex-quota-all-states.png"
    _contact_sheet(panels, output / sheet_name)
    files.append(sheet_name)

    manifest: dict[str, object] = {
        "generated_at": now.isoformat(),
        "reset_seconds": reset_seconds,
        "display_size": [240, 240],
        "full_animation_frame_times": list(FRAME_TIMES),
        "files": files,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/codex-quota-states"),
        help="Artifact directory (default: artifacts/codex-quota-states)",
    )
    parser.add_argument(
        "--now",
        type=_parse_datetime,
        default=DEFAULT_NOW,
        help="Stable ISO timestamp used for countdown rendering",
    )
    parser.add_argument(
        "--reset-seconds",
        type=int,
        default=DEFAULT_RESET_SECONDS,
        help="Seconds until weekly reset in generated examples",
    )
    args = parser.parse_args()
    if args.reset_seconds < 0:
        parser.error("--reset-seconds must be non-negative")
    manifest = generate(args.output.resolve(), args.now, args.reset_seconds)
    print(json.dumps({"output": str(args.output.resolve()), **manifest}, indent=2))


if __name__ == "__main__":
    main()
