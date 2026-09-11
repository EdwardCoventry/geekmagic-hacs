"""Tests for bounded GeekMagic firmware recovery."""

from unittest.mock import AsyncMock

import pytest

from custom_components.geekmagic.models import ConnectionResult, SpaceInfo
from custom_components.geekmagic.recovery import (
    DeviceRecovery,
    DeviceRecoveryState,
)


class FakeDevice:
    host = "192.168.0.54"

    def __init__(self, probes: list[bool]) -> None:
        self.reboot = AsyncMock()
        self._probes = iter(probes)

    async def get_space(self) -> SpaceInfo:
        if not next(self._probes):
            raise TimeoutError("still stalled")
        return SpaceInfo(total=100, free=50)


@pytest.mark.asyncio
async def test_recovery_reboots_after_three_timeouts_and_requires_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_SETTLE_SECONDS", 0)
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_PROBE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_PROBE_ATTEMPTS", 2)
    device = FakeDevice([False, True])
    recovery = DeviceRecovery(DeviceRecoveryState(consecutive_service_failures=2))

    result = await recovery.handle_failure(
        device,
        ConnectionResult(success=False, error="timeout", message="timed out"),
    )

    assert result.success is True
    device.reboot.assert_awaited_once()
    assert recovery.state.last_recovery_result == "recovered"
    assert recovery.state.consecutive_service_failures == 0


@pytest.mark.asyncio
async def test_recovery_does_not_reboot_before_threshold() -> None:
    device = FakeDevice([])
    recovery = DeviceRecovery()

    result = await recovery.handle_failure(
        device,
        ConnectionResult(success=False, error="timeout", message="timed out"),
    )

    assert result.success is False
    device.reboot.assert_not_awaited()
    assert recovery.state.consecutive_service_failures == 1


@pytest.mark.asyncio
async def test_recovery_cooldown_prevents_reboot_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_SETTLE_SECONDS", 0)
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_PROBE_ATTEMPTS", 1)
    device = FakeDevice([False])
    recovery = DeviceRecovery(DeviceRecoveryState(consecutive_service_failures=2))

    failed = ConnectionResult(success=False, error="timeout", message="timed out")
    await recovery.handle_failure(device, failed)
    await recovery.handle_failure(device, failed)

    device.reboot.assert_awaited_once()
    assert recovery.state.last_recovery_result == "failed"


@pytest.mark.asyncio
async def test_connection_refused_also_triggers_firmware_reboot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_SETTLE_SECONDS", 0)
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_PROBE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("custom_components.geekmagic.recovery.RECOVERY_PROBE_ATTEMPTS", 1)
    device = FakeDevice([True])
    recovery = DeviceRecovery(DeviceRecoveryState(consecutive_service_failures=2))

    result = await recovery.handle_failure(
        device,
        ConnectionResult(success=False, error="connection_refused", message="refused"),
    )

    assert result.success is True
    device.reboot.assert_awaited_once()
    assert recovery.state.consecutive_service_failures == 0


@pytest.mark.asyncio
async def test_dns_failure_does_not_trigger_firmware_reboot() -> None:
    device = FakeDevice([])
    recovery = DeviceRecovery(DeviceRecoveryState(consecutive_service_failures=2))

    result = await recovery.handle_failure(
        device,
        ConnectionResult(success=False, error="dns_error", message="unresolved"),
    )

    assert result.error == "dns_error"
    device.reboot.assert_not_awaited()
    assert recovery.state.consecutive_service_failures == 0
