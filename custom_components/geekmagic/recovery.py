"""Bounded recovery for a GeekMagic device whose HTTP service has stalled."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from .models import ConnectionResult

_LOGGER = logging.getLogger(__name__)

RECOVERY_FAILURE_THRESHOLD = 3
RECOVERY_COOLDOWN_SECONDS = 15 * 60
RECOVERY_REBOOT_TIMEOUT_SECONDS = 8
RECOVERY_SETTLE_SECONDS = 3
RECOVERY_PROBE_ATTEMPTS = 6
RECOVERY_PROBE_INTERVAL_SECONDS = 5


@dataclass
class DeviceRecoveryState:
    """Mutable recovery state shared by config-entry retries and coordinators."""

    consecutive_timeouts: int = 0
    last_recovery_attempt: float | None = None
    recovery_in_progress: bool = False
    last_recovery_result: str = "never_attempted"


class RecoverableDevice(Protocol):
    """Minimal device surface needed by the recovery policy."""

    host: str

    async def reboot(self) -> None:
        """Request a firmware reboot."""

    async def get_space(self) -> object:
        """Probe the device HTTP service."""


class DeviceRecovery:
    """Recover a stalled HTTP service once, then verify it before resuming."""

    def __init__(self, state: DeviceRecoveryState | None = None) -> None:
        self.state = state or DeviceRecoveryState()

    def record_success(self) -> None:
        """Clear the failure streak after a successful connection probe."""
        self.state.consecutive_timeouts = 0

    async def handle_failure(
        self,
        device: RecoverableDevice,
        result: ConnectionResult,
    ) -> ConnectionResult:
        """Maybe reboot after repeated timeouts and return a verified result."""
        if result.error != "timeout":
            self.state.consecutive_timeouts = 0
            return result

        self.state.consecutive_timeouts += 1
        if not self._should_recover():
            return result

        self.state.last_recovery_attempt = time.monotonic()
        self.state.recovery_in_progress = True
        _LOGGER.warning(
            "GeekMagic device %s HTTP service timed out %d times; "
            "issuing one bounded firmware reboot",
            device.host,
            self.state.consecutive_timeouts,
        )
        try:
            try:
                await asyncio.wait_for(
                    device.reboot(),
                    timeout=RECOVERY_REBOOT_TIMEOUT_SECONDS,
                )
            except Exception as err:
                _LOGGER.warning(
                    "GeekMagic device %s reboot request did not return cleanly: %s; "
                    "polling for recovery",
                    device.host,
                    err,
                )

            await asyncio.sleep(RECOVERY_SETTLE_SECONDS)
            for attempt in range(1, RECOVERY_PROBE_ATTEMPTS + 1):
                try:
                    await device.get_space()
                except Exception as err:
                    _LOGGER.debug(
                        "GeekMagic device %s recovery probe %d/%d failed: %s",
                        device.host,
                        attempt,
                        RECOVERY_PROBE_ATTEMPTS,
                        err,
                    )
                else:
                    self.state.consecutive_timeouts = 0
                    self.state.last_recovery_result = "recovered"
                    _LOGGER.warning(
                        "GeekMagic device %s recovered after firmware reboot; "
                        "normal display updates will resume",
                        device.host,
                    )
                    return ConnectionResult(
                        success=True,
                        message="Device recovered after an automatic firmware reboot",
                    )
                if attempt < RECOVERY_PROBE_ATTEMPTS:
                    await asyncio.sleep(RECOVERY_PROBE_INTERVAL_SECONDS)

            self.state.last_recovery_result = "failed"
            _LOGGER.error(
                "GeekMagic device %s did not recover after the bounded firmware reboot; "
                "automatic recovery is cooling down",
                device.host,
            )
            return result
        finally:
            self.state.recovery_in_progress = False

    def diagnostics(self) -> dict[str, object]:
        """Return safe recovery state for the status entity."""
        return {
            "consecutive_timeouts": self.state.consecutive_timeouts,
            "last_recovery_attempt": self.state.last_recovery_attempt,
            "recovery_in_progress": self.state.recovery_in_progress,
            "last_recovery_result": self.state.last_recovery_result,
        }

    def _should_recover(self) -> bool:
        if self.state.recovery_in_progress:
            return False
        if self.state.consecutive_timeouts < RECOVERY_FAILURE_THRESHOLD:
            return False
        if self.state.last_recovery_attempt is None:
            return True
        return time.monotonic() - self.state.last_recovery_attempt >= RECOVERY_COOLDOWN_SECONDS


__all__ = [
    "RECOVERY_COOLDOWN_SECONDS",
    "RECOVERY_FAILURE_THRESHOLD",
    "DeviceRecovery",
    "DeviceRecoveryState",
]
