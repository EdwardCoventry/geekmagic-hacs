"""Tests for the reusable Codex quota screenshot generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageChops

SCRIPT = Path(__file__).parent.parent / "scripts" / "generate_codex_quota_states.py"
SPEC = importlib.util.spec_from_file_location("generate_codex_quota_states", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_generate_writes_all_semantic_states_and_animation_frames(tmp_path: Path) -> None:
    manifest = MODULE.generate(tmp_path, MODULE.DEFAULT_NOW, MODULE.DEFAULT_RESET_SECONDS)

    expected = {
        "codex-quota-unknown.png",
        "codex-quota-empty.png",
        "codex-quota-critical-red.png",
        "codex-quota-warning-amber.png",
        "codex-quota-healthy-green.png",
        "codex-quota-full-frame-1.png",
        "codex-quota-full-frame-2.png",
        "codex-quota-full-reset.gif",
        "codex-quota-all-states.png",
    }
    assert set(manifest["files"]) == expected
    assert all((tmp_path / name).exists() for name in expected)

    for name in expected - {"codex-quota-all-states.png"}:
        with Image.open(tmp_path / name) as image:
            assert image.size == (240, 240)

    with (
        Image.open(tmp_path / "codex-quota-full-frame-1.png") as first,
        Image.open(tmp_path / "codex-quota-full-frame-2.png") as second,
    ):
        assert ImageChops.difference(first.convert("RGB"), second.convert("RGB")).getbbox()

    with Image.open(tmp_path / "codex-quota-full-reset.gif") as animation:
        assert animation.n_frames == 2
        assert animation.info["duration"] == 1000

    with Image.open(tmp_path / "codex-quota-all-states.png") as sheet:
        assert sheet.size == (780, 834)
