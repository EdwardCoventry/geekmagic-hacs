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
