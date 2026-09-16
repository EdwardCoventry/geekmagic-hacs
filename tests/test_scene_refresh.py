"""Scene chips refresh independently of polling and in-flight uploads."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.geekmagic.coordinator import GeekMagicCoordinator


@pytest.fixture
def scene_coordinator(hass):
    return GeekMagicCoordinator(
        hass,
        MagicMock(),
        {"widgets": [{
            "type": "homeberry_dashboard",
            "slot": 0,
            "options": {"scene_entity_id": "sensor.scene"},
        }]},
    )


def scene_event(old_chips, new_chips):
    return SimpleNamespace(data={
        "entity_id": "sensor.scene",
        "old_state": SimpleNamespace(state="Movie", attributes={"scene_chips": old_chips}),
        "new_state": SimpleNamespace(state="Movie", attributes={"scene_chips": new_chips}),
    })


@pytest.mark.asyncio
async def test_chip_change_bypasses_active_polling_cooldown(scene_coordinator):
    coordinator = scene_coordinator
    coordinator._async_update_display = AsyncMock(return_value={"success": True})
    await coordinator.async_request_refresh()
    with patch("custom_components.geekmagic.coordinator.async_call_later"):
        coordinator._handle_dependency_change(scene_event(["movie"], ["night", "movie"]))
        coordinator._dispatch_event_refresh(datetime.now(tz=UTC))
        await coordinator._scene_refresh_task
    assert coordinator._async_update_display.await_count == 2
    assert coordinator.event_refresh_diagnostics["last_reasons"] == ["scene"]
    coordinator.stop_event_refresh()
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_scene_change_during_upload_is_retained_and_serialized(scene_coordinator):
    coordinator = scene_coordinator
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def upload():
        calls.append("start")
        entered.set()
        await release.wait()
        calls.append("end")
        return {"success": True}

    coordinator._async_update_display = upload
    polling = asyncio.create_task(coordinator.async_request_refresh())
    await entered.wait()
    with patch("custom_components.geekmagic.coordinator.async_call_later"):
        coordinator._handle_dependency_change(scene_event([], ["movie"]))
        coordinator._dispatch_event_refresh(datetime.now(tz=UTC))
        await asyncio.sleep(0)
        assert calls == ["start"]
        coordinator._handle_dependency_change(scene_event(["movie"], ["night", "movie"]))
        coordinator._dispatch_event_refresh(datetime.now(tz=UTC))
        release.set()
        await polling
        await coordinator._scene_refresh_task
    assert calls == ["start", "end"] * 3
    coordinator.stop_event_refresh()
    await coordinator.async_shutdown()


def test_unchanged_chips_do_not_get_scene_priority(scene_coordinator):
    with patch("custom_components.geekmagic.coordinator.async_call_later"):
        scene_coordinator._handle_dependency_change(scene_event(["movie"], ["movie"]))
    assert scene_coordinator._pending_event_refresh_reasons == {"entity"}
    scene_coordinator.stop_event_refresh()


@pytest.mark.asyncio
async def test_live_state_event_with_same_top_scene_refreshes_chips(hass, scene_coordinator):
    coordinator = scene_coordinator
    coordinator._async_update_display = AsyncMock(return_value={"success": True})
    hass.states.async_set("sensor.scene", "Movie", {"scene_chips": ["movie"]})
    await hass.async_block_till_done()
    coordinator.start_event_refresh()
    await coordinator.async_request_refresh()
    hass.states.async_set("sensor.scene", "Movie", {"scene_chips": ["night", "movie"]})
    await hass.async_block_till_done()
    await asyncio.sleep(0.3)
    await hass.async_block_till_done()
    assert coordinator._async_update_display.await_count == 2
    assert coordinator.event_refresh_diagnostics["last_reasons"] == ["scene"]
    coordinator.stop_event_refresh()
    await coordinator.async_shutdown()
