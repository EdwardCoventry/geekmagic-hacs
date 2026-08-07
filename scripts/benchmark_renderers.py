#!/usr/bin/env python3
"""Benchmark the layered renderer against the legacy compositing path.

"New" is the engine-side pipeline: one ``render_layers`` call composites
the backdrop, every widget cell, and the theme overlay. "Legacy" is the
pre-0.4.0 fallback still in-tree (``Layout._render_legacy``): one
``render_document`` call per pass plus Pillow premultiplied compositing.
Both run on the same installed blitz-py, so the comparison isolates the
compositing strategy — process-wide font registration benefits both
paths equally (the true pre-0.4.0 experience also paid per-call font
bytes, so legacy numbers here are flattering).

The legacy path is forced by patching ``layouts.base.HAS_LAYERS`` (the
name is bound there at import time). Each scenario is verified before
timing: the new path must not fall through to legacy, the legacy path
must actually paint cells, and the two outputs must be near-identical.

Usage:
    uv run python scripts/benchmark_renderers.py [--iterations 20]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import ImageChops, ImageStat

from custom_components.geekmagic.layouts import base as layouts_base
from custom_components.geekmagic.layouts.fullscreen import FullscreenLayout
from custom_components.geekmagic.layouts.grid import Grid2x2, Grid3x3
from custom_components.geekmagic.layouts.hero import HeroLayout
from custom_components.geekmagic.renderer import Renderer
from custom_components.geekmagic.widgets import WIDGET_CLASSES
from custom_components.geekmagic.widgets.base import WidgetConfig
from custom_components.geekmagic.widgets.state import EntityState, WidgetState
from custom_components.geekmagic.widgets.theme import THEMES

if TYPE_CHECKING:
    from PIL import Image

    from custom_components.geekmagic.layouts.base import Layout

NOW = datetime(2026, 8, 7, 18, 45, 30, tzinfo=UTC)

# Mean per-pixel RGB delta allowed between the two paths. Compositing
# rounding differs (engine f32 vs Pillow uint8 premultiply), but the
# same cells at the same rects must produce visually identical screens.
PARITY_BUDGET = 3.0


def _widget(widget_type: str, slot: int, **kwargs) -> object:
    options = kwargs.pop("options", {})
    config = WidgetConfig(widget_type=widget_type, slot=slot, options=options, **kwargs)
    return WIDGET_CLASSES[widget_type](config)


def _sensor(entity_id: str, state: object, name: str, unit: str | None = None) -> EntityState:
    attributes: dict[str, object] = {"friendly_name": name}
    if unit:
        attributes["unit_of_measurement"] = unit
    return EntityState(entity_id=entity_id, state=str(state), attributes=attributes)


def _state(entity: EntityState | None = None, history: list[float] | None = None) -> WidgetState:
    return WidgetState(entity=entity, history=history or [], now=NOW)


def _mixed_grid2x2() -> tuple[Layout, dict[int, WidgetState]]:
    layout = Grid2x2()
    layout.set_widget(0, _widget("chart", 0, label="CPU"))
    layout.set_widget(1, _widget("gauge", 1, options={"style": "bar"}))
    layout.set_widget(2, _widget("gauge", 2, options={"style": "ring"}))
    layout.set_widget(3, _widget("entity", 3))
    history = [42.0, 48.0, 51.0, 47.0, 55.0, 61.0, 58.0, 64.0, 60.0, 66.0, 71.0, 68.0]
    states = {
        0: _state(_sensor("sensor.cpu", 68, "CPU", "%"), history),
        1: _state(_sensor("sensor.memory", 74, "Memory", "%")),
        2: _state(_sensor("sensor.disk", 41, "Disk", "%")),
        3: _state(_sensor("sensor.power", 235, "Power", "W")),
    }
    return layout, states


def _entity_grid3x3() -> tuple[Layout, dict[int, WidgetState]]:
    layout = Grid3x3()
    states = {}
    for i in range(9):
        layout.set_widget(i, _widget("entity", i))
        states[i] = _state(_sensor(f"sensor.s{i}", 10 * i + 3, f"Sensor {i}", "°C"))
    return layout, states


def _hero() -> tuple[Layout, dict[int, WidgetState]]:
    layout = HeroLayout()
    layout.set_widget(0, _widget("clock", 0))
    layout.set_widget(1, _widget("entity", 1))
    layout.set_widget(2, _widget("entity", 2))
    states = {
        0: _state(),
        1: _state(_sensor("sensor.temp", 21.5, "Inside", "°C")),
        2: _state(_sensor("sensor.hum", 47, "Humidity", "%")),
    }
    return layout, states


def _fullscreen_clock() -> tuple[Layout, dict[int, WidgetState]]:
    layout = FullscreenLayout()
    layout.set_widget(0, _widget("clock", 0, options={"show_date": True}))
    return layout, {0: _state()}


# (name, theme label, factory, parity budget). Glow gets a looser
# budget: legacy has no blurred-underlay pass, so neon screens are
# legitimately dimmer there — a fidelity gap, not a benchmark artifact.
SCENARIOS: list[tuple[str, str, object, float]] = [
    ("fullscreen clock", "watchos", _fullscreen_clock, PARITY_BUDGET),
    ("hero (3 cells)", "watchos", _hero, PARITY_BUDGET),
    ("grid 2x2 mixed", "watchos", _mixed_grid2x2, PARITY_BUDGET),
    ("grid 3x3 entities", "watchos", _entity_grid3x3, PARITY_BUDGET),
    ("grid 2x2 mixed", "neon (glow)", _mixed_grid2x2, 8.0),
    ("grid 2x2 mixed", "retro (overlay)", _mixed_grid2x2, PARITY_BUDGET),
]


def _build(scenario_factory, theme_key: str) -> tuple[Layout, dict[int, WidgetState]]:
    layout, states = scenario_factory()
    layout.theme = THEMES[theme_key.split(" ", maxsplit=1)[0]]
    return layout, states


def _render_once(renderer: Renderer, layout: Layout, states: dict[int, WidgetState]) -> Image.Image:
    img, draw = renderer.create_canvas()
    layout.render(renderer, draw, states)
    return img


def _verify_paths(
    renderer: Renderer,
    layout: Layout,
    states: dict[int, WidgetState],
    parity_budget: float,
) -> float:
    """Fail loudly if either path silently degrades (renders nothing or
    falls back), which would make its timing meaningless."""
    with patch.object(layouts_base, "render_document", side_effect=AssertionError) as legacy_calls:
        new_img = _render_once(renderer, layout, states)
    if legacy_calls.called:
        msg = "new path fell through to legacy rendering"
        raise RuntimeError(msg)

    with patch.object(layouts_base, "HAS_LAYERS", new=False):
        legacy_img = _render_once(renderer, layout, states)

    for name, img in (("new", new_img), ("legacy", legacy_img)):
        if len(img.getcolors(16) or [0, 0]) <= 1:
            msg = f"{name} path produced a blank canvas"
            raise RuntimeError(msg)

    diff = ImageChops.difference(new_img.convert("RGB"), legacy_img.convert("RGB"))
    mean_delta = sum(ImageStat.Stat(diff).mean) / 3.0
    if mean_delta > parity_budget:
        msg = f"paths diverge: mean per-pixel delta {mean_delta:.2f} > {parity_budget}"
        raise RuntimeError(msg)
    return mean_delta


def _time_path(
    renderer: Renderer,
    layout: Layout,
    states: dict[int, WidgetState],
    iterations: int,
    *,
    legacy: bool,
) -> list[float]:
    def run() -> None:
        _render_once(renderer, layout, states)

    if legacy:
        with patch.object(layouts_base, "HAS_LAYERS", new=False):
            return _timeit(run, iterations)
    return _timeit(run, iterations)


def _timeit(fn, iterations: int) -> list[float]:
    for _ in range(2):  # warmup: font registration, engine init, caches
        fn()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    if not layouts_base.HAS_LAYERS:
        msg = "installed blitz-py lacks render_layers; nothing to compare"
        raise SystemExit(msg)

    renderer = Renderer()
    print(f"blitz-py layered vs legacy — {args.iterations} iterations per path")
    print(f"canvas {renderer.width}x{renderer.height} @ {renderer.scale}x supersample\n")
    header = (
        f"{'scenario':<22} {'theme':<16} {'new (ms)':>14} {'legacy (ms)':>14}"
        f" {'speedup':>8} {'Δpx':>6}"
    )
    print(header)
    print("-" * len(header))

    for name, theme_label, factory, parity_budget in SCENARIOS:
        layout, states = _build(factory, theme_label)
        delta = _verify_paths(renderer, layout, states, parity_budget)
        new_samples = _time_path(renderer, layout, states, args.iterations, legacy=False)
        legacy_samples = _time_path(renderer, layout, states, args.iterations, legacy=True)
        new_med = statistics.median(new_samples) * 1000
        legacy_med = statistics.median(legacy_samples) * 1000
        new_stdev = statistics.stdev(new_samples) * 1000
        legacy_stdev = statistics.stdev(legacy_samples) * 1000
        print(
            f"{name:<22} {theme_label:<16} "
            f"{new_med:>8.1f} ±{new_stdev:>4.1f} "
            f"{legacy_med:>8.1f} ±{legacy_stdev:>4.1f} "
            f"{legacy_med / new_med:>7.2f}x {delta:>6.2f}"
        )


if __name__ == "__main__":
    main()
