# GeekMagic HTTP recovery

The integration treats repeated HTTP-service failures differently from DNS or
network-configuration errors because the SmallTV-Ultra can remain reachable by
ICMP while its HTTP service stops answering. After three consecutive timeouts,
refused connections, HTTP errors, or unexpected service failures, a configured
Home Assistant entry sends the firmware's documented `/set?reboot=1` request
and then polls `/space.json` six times for recovery.

The reboot request is bounded to eight seconds. A device may close that socket
as it restarts, so a clean reboot response is not required; recovery is only
reported after a fresh probe succeeds. Each probe is independently bounded to
eight seconds. If all probes fail, the original connection failure remains
visible and no upload is attempted.

Recovery has a 15-minute per-host cooldown shared across Home Assistant config
entry retries and integration reloads. DNS failures do not trigger a reboot,
because they indicate a name-resolution/configuration problem rather than a
stalled device service. The status sensor exposes the service-failure streak,
last recovery outcome, and whether recovery is currently running.

This is network-level recovery only. If the device does not accept the reboot
request, physical power cycling remains the hardware boundary and is not
automated by this integration.
