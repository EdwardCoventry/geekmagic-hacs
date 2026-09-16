# Pixel brightness

Each display exposes a **Pixel Brightness** number (0–100%). It multiplies all
rendered RGB channels before JPEG/GIF encoding. This supplements the separate
hardware Brightness number when minimum backlight is still too bright.

The setting is persisted in config-entry options as `pixel_brightness`. It
applies to every still image, every animation frame, notifications, and previews.
Fresh rendering always starts from undimmed source pixels: dimming never compounds
between updates. Zero gives black pixels; 100 preserves the original image.

The number's state reports the factor last successfully uploaded. Failed uploads
leave the previous applied value, allowing Homeberry to detect and retry them.
Before the first successful upload it is unknown. Built-in firmware screens and
paused displays do not run the renderer, so software dimming requires an active
custom view. LCD backlight leakage cannot be removed by changing pixel values.

Homeberry's signed scale uses hardware brightness above zero and this control
below zero: -180 means hardware 0%, pixels 10%; -200 means black. Automatic
Homeberry control stops at -180. Install/reload this integration before deploying
the corresponding Homeberry controller, and verify the Pixel Brightness entity ID
in Homeberry's brightness config.

Validation: `uv run python -m pytest tests/test_pixel_brightness.py tests/test_coordinator.py -q`.
