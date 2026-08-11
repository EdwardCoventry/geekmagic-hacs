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


def test_hotter_temperature_renders_as_a_single_red_chip(tmp_path: Path):
    manifest = MODULE.generate(tmp_path)

    assert manifest["temperature_storyboard_order"] == [
        "out-hotter",
        "in-hotter",
        "equal-displayed",
    ]

    def has_red_chip(
        image: Image.Image, box: tuple[int, int, int, int]
    ) -> bool:
        red_pixels = sum(
            red > 180 and green < 120 and blue < 120
            for red, green, blue in image.convert("RGB").crop(box).getdata()
        )
        return red_pixels > 100

    with (
        Image.open(
            tmp_path / "homeberry-dashboard-temperature-out-hotter.png"
        ) as out_hotter,
        Image.open(tmp_path / "homeberry-dashboard-temperature-in-hotter.png") as in_hotter,
        Image.open(
            tmp_path / "homeberry-dashboard-temperature-equal-displayed.png"
        ) as equal,
    ):
        out_chip = (145, 68, 184, 89)
        in_chip = (145, 104, 184, 125)
        assert has_red_chip(out_hotter, out_chip)
        assert not has_red_chip(out_hotter, in_chip)
        assert not has_red_chip(in_hotter, out_chip)
        assert has_red_chip(in_hotter, in_chip)
        assert not has_red_chip(equal, out_chip)
        assert not has_red_chip(equal, in_chip)


def test_dashboard_visual_bands_have_identical_six_pixel_gaps(tmp_path: Path):
    manifest = MODULE.generate(tmp_path)
    report = manifest["visual_spacing"]

    assert (tmp_path / "homeberry-dashboard-spacing-diagnostic.png").is_file()
    assert (tmp_path / "homeberry-dashboard-spacing-report.json").is_file()
    assert [gap["pixels"] for gap in report["gaps"]] == [6, 6, 6, 6, 6], "\n".join(
        report["recommendations"]
    )
    assert report["passed"] is True


def test_visual_spacing_is_stable_across_dynamic_dashboard_states(tmp_path: Path):
    manifest = MODULE.generate(tmp_path)
    failures = []
    for family in ("thermal_visual_spacing", "temperature_visual_spacing"):
        for state_name, report in manifest[family].items():
            if not report["passed"]:
                failures.extend(
                    f"{family}/{state_name}: {recommendation}"
                    for recommendation in report["recommendations"]
                )

    assert not failures, "\n".join(failures)
