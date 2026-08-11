"""Tests for Homeberry dashboard preview generation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageChops

SCRIPT = Path(__file__).parent.parent / "scripts" / "generate_homeberry_dashboard_states.py"
SPEC = importlib.util.spec_from_file_location("generate_homeberry_dashboard_states", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_generator_writes_dashboard_and_both_reset_frames(tmp_path: Path):
    manifest = MODULE.generate(tmp_path)

    assert manifest["display_size"] == [240, 240]
    expected = {
        "homeberry-dashboard-normal.png",
        "homeberry-dashboard-full-frame-1.png",
        "homeberry-dashboard-full-frame-2.png",
        "homeberry-dashboard-full-reset.gif",
        "homeberry-dashboard-storyboard.png",
    }
    assert expected <= {path.name for path in tmp_path.iterdir()}

    with (
        Image.open(tmp_path / "homeberry-dashboard-full-frame-1.png") as first,
        Image.open(tmp_path / "homeberry-dashboard-full-frame-2.png") as second,
    ):
        assert first.size == second.size == (240, 240)
        assert ImageChops.difference(first.convert("RGB"), second.convert("RGB")).getbbox()

    with Image.open(tmp_path / "homeberry-dashboard-full-reset.gif") as animation:
        assert animation.n_frames == 2
        assert animation.info["duration"] == 1000


def test_temperature_comparison_outlines_render_into_output_pixels(tmp_path: Path):
    manifest = MODULE.generate(tmp_path)

    assert manifest["temperature_storyboard_order"] == [
        "out-hotter",
        "in-hotter",
        "equal-displayed",
    ]

    def has_outline_edges(
        image: Image.Image,
        top_box: tuple[int, int, int, int],
        bottom_box: tuple[int, int, int, int],
    ) -> bool:
        rgb = image.convert("RGB")
        return all(
            min(pixel) > 180
            for box in (top_box, bottom_box)
            for pixel in rgb.crop(box).getdata()
        )

    with (
        Image.open(
            tmp_path / "homeberry-dashboard-temperature-out-hotter.png"
        ) as out_hotter,
        Image.open(tmp_path / "homeberry-dashboard-temperature-in-hotter.png") as in_hotter,
        Image.open(
            tmp_path / "homeberry-dashboard-temperature-equal-displayed.png"
        ) as equal,
    ):
        out_outline = ((151, 67, 171, 68), (151, 88, 171, 89))
        in_outline = ((151, 100, 171, 101), (151, 121, 171, 122))
        assert has_outline_edges(out_hotter, *out_outline)
        assert not has_outline_edges(out_hotter, *in_outline)
        assert not has_outline_edges(in_hotter, *out_outline)
        assert has_outline_edges(in_hotter, *in_outline)
        assert has_outline_edges(equal, *out_outline)
        assert has_outline_edges(equal, *in_outline)
