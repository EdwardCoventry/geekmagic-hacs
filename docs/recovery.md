# GeekMagic HTTP recovery

The integration treats repeated HTTP timeouts differently from ordinary
connection errors because the SmallTV-Ultra can remain reachable by ICMP while
its HTTP service stops answering. After three consecutive `/space.json`
timeouts, a configured Home Assistant entry sends the firmware's documented
`/set?reboot=1` request and then polls `/space.json` six times for recovery.

The reboot request is bounded to eight seconds. A device may close that socket
as it restarts, so a clean reboot response is not required; recovery is only
reported after a fresh probe succeeds. If all probes fail, the original timeout
remains a visible connection failure and no upload is attempted.

Recovery has a 15-minute per-host cooldown shared across Home Assistant config
entry retries and integration reloads. DNS failures, refused connections, and
HTTP errors do not trigger a reboot because they do not establish that the
firmware HTTP service is stalled. The status sensor exposes the timeout streak,
last recovery outcome, and whether recovery is currently running.

This is network-level recovery only. If the device does not accept the reboot
request, physical power cycling remains the hardware boundary and is not
automated by this integration.
