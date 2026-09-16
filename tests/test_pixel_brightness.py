"""Pixel dimming covers the actual encoded display and preview paths."""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from custom_components.geekmagic.coordinator import GeekMagicCoordinator


@pytest.mark.parametrize("factor", [0, 10, 50, 100])
def test_still_pixel_dimming(hass, factor, monkeypatch):
    coordinator = GeekMagicCoordinator(hass, MagicMock(), {})
    layout = MagicMock()
    layout.theme.background = (200, 100, 40)
    layout.slots = []
    coordinator._layouts = [layout]
    monkeypatch.setattr(coordinator, "_build_widget_states", lambda _: {})
    _, preview, filename = coordinator._render_display(factor)
    image = Image.open(BytesIO(preview)).convert("RGB")
    assert image.getpixel((100, 100)) == tuple(int(c * factor / 100) for c in (200, 100, 40))
    assert filename == "dashboard.jpg"
    # Never modify the original canvas or compound dimming between refreshes.
    _, restored, _ = coordinator._render_display(100)
    assert Image.open(BytesIO(restored)).convert("RGB").getpixel((100, 100)) == (200, 100, 40)


def test_animation_dims_every_frame(hass, monkeypatch):
    import custom_components.geekmagic.coordinator as module

    monkeypatch.setattr(module, "HAS_FRAMES", True)
    coordinator = GeekMagicCoordinator(hass, MagicMock(), {"enable_animations": True})
    layout = MagicMock()
    layout.slots = []
    layout.has_animated_widgets.return_value = True
    layout.render_animation.return_value = [
        Image.new("RGB", (240, 240), color) for color in [(200, 100, 40), (100, 200, 80)]
    ]
    coordinator._layouts = [layout]
    coordinator._animation_renderer_warmed = True
    monkeypatch.setattr(coordinator, "_build_widget_states", lambda _: {})
    coordinator.options[module.CONF_ENABLE_ANIMATIONS] = True
    frames = []

    def encode(images, **kwargs):
        frames.extend(images)
        return b"GIF"

    monkeypatch.setattr(coordinator.renderer, "to_gif", encode)
    _, preview, filename = coordinator._render_display(10)
    assert filename == "dashboard.gif"
    assert [frame.getpixel((100, 100)) for frame in frames] == [(20, 10, 4), (10, 20, 8)]
    assert Image.open(BytesIO(preview)).convert("RGB").getpixel((100, 100)) == (20, 10, 4)


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_pixel_readback_advances_only_after_upload(hass, monkeypatch, fails):
    from unittest.mock import AsyncMock

    from homeassistant.helpers.update_coordinator import UpdateFailed

    device = MagicMock()
    device.get_brightness = AsyncMock(return_value=0)
    device.get_state = AsyncMock(return_value=None)
    device.get_space = AsyncMock(return_value=None)
    device.display_rendered_dashboard = AsyncMock(
        side_effect=OSError("upload failed") if fails else None
    )
    coordinator = GeekMagicCoordinator(hass, device, {"pixel_brightness": 10})
    coordinator.applied_pixel_brightness = 100
    for method in (
        "_async_fetch_camera_images",
        "_async_fetch_media_images",
        "_async_fetch_chart_history",
        "_async_fetch_candlestick_history",
        "_async_fetch_weather_forecasts",
    ):
        monkeypatch.setattr(coordinator, method, AsyncMock())
    render = MagicMock(return_value=(b"jpeg", b"png", "dashboard.jpg"))
    monkeypatch.setattr(coordinator, "_render_display", render)
    if fails:
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.applied_pixel_brightness == 100
    else:
        await coordinator._async_update_data()
        assert coordinator.applied_pixel_brightness == 10
    render.assert_called_once_with(10)
