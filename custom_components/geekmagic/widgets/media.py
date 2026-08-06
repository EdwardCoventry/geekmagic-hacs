"""Media player widget for GeekMagic displays."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import TYPE_CHECKING, Any, ClassVar

from ..htmldoc import css_rgb, image_data_uri, mdi_span

if TYPE_CHECKING:
    from PIL import Image

    from ..htmldoc import CellContext
    from .state import EntityState, WidgetState

from .base import Widget, WidgetConfig
from .helpers import truncate_text


def _fit_chars(width_px: float, min_px: float, vmin_px: float, max_px: float) -> int:
    """Estimate chars fitting in ``width_px`` for a clamp()-sized font.

    Blitz doesn't render ``text-overflow: ellipsis``, so single-line text
    is truncated Python-side. Mirrors ``clamp(min_px, vmin_px, max_px)``
    and assumes an average glyph width of ~0.55em (Nunito, mixed case).
    """
    font_px = min(max_px, max(min_px, vmin_px))
    return max(4, int(width_px / (font_px * 0.55)))


def _calculate_media_position(
    entity: EntityState | None,
    now: datetime | None,
) -> float:
    """Calculate current media position accounting for elapsed playback time.

    Home Assistant's media_position only updates on state changes (play/pause/seek).
    To get the actual current position, we need to add elapsed time since the
    last update when the player is actively playing.

    Args:
        entity: Media player entity state
        now: Current datetime (timezone-aware)

    Returns:
        Current position in seconds
    """
    if entity is None:
        return 0.0

    # Get base position
    position = float(entity.get("media_position", 0) or 0)

    # Only calculate elapsed time if playing and we have timing info
    if entity.state != "playing" or now is None:
        return position

    # Get the timestamp when position was last updated
    updated_at = entity.get("media_position_updated_at")
    if updated_at is None:
        return position

    # Parse the datetime if it's a string (HA stores as ISO format)
    if isinstance(updated_at, str):
        try:
            updated_at = datetime.fromisoformat(updated_at)
        except (ValueError, TypeError):
            return position

    # Calculate elapsed time since last update
    if hasattr(updated_at, "timestamp"):
        elapsed = now.timestamp() - updated_at.timestamp()
        if elapsed > 0:
            # Add elapsed time, but cap at duration if available
            duration = float(entity.get("media_duration", 0) or 0)
            new_position = position + elapsed
            return min(new_position, duration) if duration > 0 else new_position

    return position


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    seconds = int(seconds)
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


def _progress_bar_html(percent: float, color: str, *, height_css: str, track: str) -> str:
    """A slim rounded progress bar with a neutral track."""
    percent = max(0.0, min(100.0, percent))
    return (
        f'<div style="width: 100%; height: {height_css}; border-radius: 999px; '
        f'background: {track}; overflow: hidden">'
        f'<div style="width: {percent:.1f}%; height: 100%; border-radius: 999px; '
        f'background: {color}"></div></div>'
    )


class MediaWidget(Widget):
    """Widget that displays media player information."""

    WIDGET_TYPE: ClassVar[str] = "media"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "Media Player",
        "needs_entity": True,
        "entity_domains": ["media_player"],
        "options": [
            {"key": "show_artist", "type": "boolean", "label": "Show Artist", "default": True},
            {"key": "show_album", "type": "boolean", "label": "Show Album", "default": False},
            {"key": "show_progress", "type": "boolean", "label": "Show Progress", "default": True},
        ],
    }

    def __init__(self, config: WidgetConfig) -> None:
        """Initialize the media widget."""
        super().__init__(config)
        self.show_artist = config.options.get("show_artist", True)
        self.show_album = config.options.get("show_album", False)
        self.show_progress = config.options.get("show_progress", True)
        self.show_album_art = config.options.get("show_album_art", True)

    def render_html(self, ctx: CellContext, state: WidgetState) -> str:
        """Render the media player widget."""
        entity = state.entity

        if entity is None or entity.state in ("off", "unavailable", "unknown", "idle", "paused"):
            return self._render_idle(entity)

        # Calculate current position (accounts for elapsed playback time)
        position = _calculate_media_position(entity, state.now)
        duration = float(entity.get("media_duration", 0) or 0)

        accent = css_rgb(self.config.color) if self.config.color else ctx.accent()

        # Use album art if available and enabled
        if self.show_album_art and state.image is not None:
            return self._render_album_art(
                ctx, entity, state.image, position=position, duration=duration, accent=accent
            )

        return self._render_now_playing(ctx, entity, position, duration, accent)

    def _render_idle(self, entity: EntityState | None) -> str:
        """Idle / paused / off placeholder."""
        if entity is not None and entity.state == "paused":
            icon, label = "pause", "PAUSED"
        else:
            icon, label = "music", "NO MEDIA"
        return (
            '<div class="cell" style="justify-content: center; gap: 4vmin; '
            'color: var(--text-secondary)">'
            f"{mdi_span(icon, 'icon i-lg')}"
            f'<div class="t-label hide-short" style="color: var(--text-secondary)">'
            f"{escape(label)}</div>"
            "</div>"
        )

    def _render_album_art(
        self,
        ctx: CellContext,
        entity: EntityState,
        image: Image.Image,
        *,
        position: float,
        duration: float,
        accent: str,
    ) -> str:
        """Full-bleed album art with bottom gradient overlay and track info.

        Spotify / Apple Music now-playing pattern: the art fills the cell, a
        fade-to-black gradient anchors the metadata at the bottom, and a slim
        tinted progress bar sits on the very bottom edge.

        Overlay text deliberately uses fixed near-white colours, NOT theme
        tokens: it renders on a dark gradient over photographic content, so
        it needs white-ish contrast regardless of theme. This is the
        documented exception to "use theme tokens for everything".
        """
        if image.mode != "RGB":
            image = image.convert("RGB")
        uri = image_data_uri(image)

        show_artist = ctx.height >= 130
        show_time = ctx.height >= 200 and duration > 0
        show_bar = self.show_progress and duration > 0

        vmin = min(ctx.width, ctx.height)
        text_width = ctx.width * 0.90  # 5% padding each side

        lines: list[str] = []
        title = entity.get("media_title", "")
        if title:
            title = truncate_text(title, _fit_chars(text_width, 10, 0.09 * vmin, 20))
            lines.append(
                '<div style="font-size: clamp(10px, 9vmin, 20px); font-weight: 700; '
                "color: rgb(255, 255, 255); max-width: 100%; overflow: hidden; "
                'white-space: nowrap; text-overflow: ellipsis">'
                f"{escape(title)}</div>"
            )
        artist = entity.get("media_artist", "")
        if artist and show_artist:
            artist = truncate_text(artist, _fit_chars(text_width, 9, 0.07 * vmin, 15))
            lines.append(
                '<div style="font-size: clamp(9px, 7vmin, 15px); font-weight: 600; '
                "color: rgba(255,255,255,0.75); max-width: 100%; overflow: hidden; "
                'white-space: nowrap; text-overflow: ellipsis">'
                f"{escape(artist)}</div>"
            )
        if show_time:
            time_str = f"{_format_time(position)} / {_format_time(duration)}"
            lines.append(
                '<div style="font-size: clamp(9px, 6vmin, 13px); font-weight: 600; '
                'color: rgba(255,255,255,0.55)">'
                f"{escape(time_str)}</div>"
            )

        text_block = ""
        if lines:
            bar_gap = "3.5%" if show_bar else "0%"
            text_block = (
                f'<div style="position: absolute; left: 0; right: 0; bottom: {bar_gap}; '
                "padding: 3% 5%; display: flex; flex-direction: column; "
                'align-items: flex-start; gap: 2px; text-align: left">'
                f"{''.join(lines)}</div>"
            )

        bar = ""
        if show_bar:
            percent = min(100.0, position / duration * 100)
            bar = (
                '<div style="position: absolute; left: 0; right: 0; bottom: 0; '
                f'height: 2.2%; background: rgba(255,255,255,0.25)">'
                f'<div style="width: {percent:.1f}%; height: 100%; '
                f'background: {accent}"></div></div>'
            )

        return (
            '<div style="position: relative; width: 100%; height: 100%; overflow: hidden">'
            f'<img src="{uri}" style="position: absolute; inset: 0; width: 100%; '
            'height: 100%; object-fit: cover">'
            '<div style="position: absolute; left: 0; right: 0; bottom: 0; height: 60%; '
            "background: linear-gradient(to bottom, rgba(0,0,0,0) 0%, "
            'rgba(0,0,0,0.55) 45%, rgba(0,0,0,0.85) 100%)"></div>'
            f"{text_block}"
            f"{bar}"
            "</div>"
        )

    def _render_now_playing(
        self,
        ctx: CellContext,
        entity: EntityState,
        position: float,
        duration: float,
        accent: str,
    ) -> str:
        """Text-only now-playing card (no album art)."""
        vmin = min(ctx.width, ctx.height)
        text_width = ctx.width * 0.88  # 6% padding each side

        bands: list[str] = ['<div class="t-label hide-short">NOW PLAYING</div>']

        title = entity.get("media_title", "Unknown")
        # Title wraps to two lines; truncate anything past that budget.
        title = truncate_text(title, 2 * _fit_chars(text_width, 12, 0.14 * vmin, 26))
        bands.append(
            '<div style="font-size: clamp(12px, 14vmin, 26px); font-weight: 700; '
            "line-height: 1.15; max-width: 100%; max-height: 2.35em; "
            'overflow: hidden; overflow-wrap: break-word">'
            f"{escape(title)}</div>"
        )

        artist = entity.get("media_artist", "")
        if self.show_artist and artist:
            artist = truncate_text(artist, _fit_chars(text_width, 10, 0.10 * vmin, 18))
            bands.append(
                '<div class="hide-short" style="font-size: clamp(10px, 10vmin, 18px); '
                "font-weight: 600; color: var(--text-secondary); max-width: 100%; "
                'overflow: hidden; white-space: nowrap; text-overflow: ellipsis">'
                f"{escape(artist)}</div>"
            )

        album = entity.get("media_album_name", "")
        if self.show_album and album:
            album = truncate_text(album, _fit_chars(text_width, 10, 0.09 * vmin, 15))
            bands.append(
                '<div class="hide-small" style="font-size: clamp(10px, 9vmin, 15px); '
                "font-weight: 600; color: var(--text-secondary); max-width: 100%; "
                'overflow: hidden; white-space: nowrap; text-overflow: ellipsis">'
                f"{escape(album)}</div>"
            )

        if self.show_progress and duration > 0:
            percent = min(100.0, position / duration * 100)
            bands.append(
                '<div style="width: 100%">'
                + _progress_bar_html(
                    percent,
                    accent,
                    height_css="clamp(3px, 3.5vmin, 6px)",
                    track="rgba(255,255,255,0.18)",
                )
                # hide-short must sit on an element without an inline
                # display (inline style would beat the media query).
                + '<div class="hide-short">'
                '<div style="display: flex; justify-content: space-between; '
                "color: var(--text-secondary); font-size: clamp(9px, 8vmin, 14px); "
                'font-weight: 600; margin-top: 2.5vmin">'
                f"<span>{escape(_format_time(position))}</span>"
                f"<span>{escape(_format_time(duration))}</span>"
                "</div></div></div>"
            )

        return f'<div class="cell" style="padding: 4% 6%">{"".join(bands)}</div>'
