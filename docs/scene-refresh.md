# Homeberry scene refresh

The Homeberry dashboard watches its configured `scene_entity_id`. Changes to
the state, `scene_chips`, `active_scene_modes`, or `resolved_scene` trigger a
priority refresh after the existing 250 ms event coalescing window. Changes
to timestamps and other telemetry retain ordinary refresh throttling.

Scene refreshes bypass Home Assistant's request-refresh cooldown. A scene
change received while a scene refresh is running leaves another refresh
pending. Polling, manual refreshes, and scene refreshes share an upload lock,
so the device receives one upload at a time. A queued refresh reads current
state after acquiring that lock. Stopping event refresh cancels its scene task.

This removes the polling cooldown from scene feedback; Homeberry publication,
rendering, and the physical image transfer still take time. Diagnostics under
`geekmagic/devices/list` report `scene` in `event_refresh.last_reasons` when
scene changes dispatch a refresh. That reports dispatch, not physical upload
completion.

Regression coverage is in `tests/test_scene_refresh.py` and
`tests/test_coordinator.py`, including unchanged top-scene names, an active
polling cooldown, and scene changes during an upload.
