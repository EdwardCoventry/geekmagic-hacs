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

# ---------------------------------------------------------------------------
# Text metrics
#
# Blitz renders no ``text-overflow: ellipsis`` and does not clip text with
# ``overflow: hidden``, so every string is fitted in Python. The constants
# below are *measured* average glyph advances (em per character) for
# mixed-case strings in the two embedded families, plus a small safety
# margin: Nunito ~0.452, DejaVu Sans ~0.551. Being slightly pessimistic
# guarantees the engine always fits at least as much as we assumed, so a
# block never grows an unplanned extra line.
# ---------------------------------------------------------------------------
_AVG_ROUNDED = 0.47
_AVG_WIDE = 0.58

# Shared inset for the album-art overlay: text, progress bar and label all
# align to the same optical margin on every cell size.
_INSET = "clamp(5px, 5.5vmin, 14px)"
_ART_BAR_H = "clamp(2px, 1.4vmin, 4px)"


def _avg_glyph(ctx: CellContext) -> float:
    """Average glyph advance (in em) for the theme's body font."""
    return _AVG_ROUNDED if getattr(ctx.theme, "rounded_font", True) else _AVG_WIDE


def _clamp_px(min_px: float, vmin_ratio: float, max_px: float, vmin: float) -> float:
    """Python mirror of ``clamp(min_px, <ratio>vmin, max_px)``."""
    return min(max_px, max(min_px, vmin_ratio * vmin))


def _inset_px(ctx: CellContext) -> float:
    """Python mirror of :data:`_INSET`."""
    return _clamp_px(5.0, 0.055, 14.0, min(ctx.width, ctx.height))


def _fit_chars(width_px: float, font_px: float, avg: float) -> int:
    """How many characters of ``font_px`` text fit into ``width_px``."""
    return max(3, int(width_px / (font_px * avg)))


def _fit_lines(text: str, per_line: int, max_lines: int) -> str:
    """Greedy-wrap ``text`` and hard-truncate it to ``max_lines`` lines.

    Returned as a single string — the engine re-wraps it at the same
    budget. Because ``per_line`` comes from a pessimistic glyph advance,
    the rendered block never overflows the line count assumed here.
    """
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current = ""
    overflowed = False
    for word in words:
        chunk = truncate_text(word, per_line)  # a word longer than a whole line
        candidate = f"{current} {chunk}" if current else chunk
        if len(candidate) <= per_line:
            current = candidate
        elif len(lines) + 1 < max_lines:
            lines.append(current)
            current = chunk
        else:
            overflowed = True
            break
    lines.append(current)
    if overflowed:
        lines[-1] = truncate_text(f"{lines[-1]}…", per_line)
    return " ".join(lines)


def _fit_title(
    text: str,
    avail_px: float,
    avg: float,
    *,
    max_px: float,
    max_lines: int,
    min_px: float = 11.0,
) -> tuple[str, float]:
    """Pick a font size and wrap/truncate a title to fill ``avail_px``.

    Short titles grow to ``max_px`` (hero dominance); long ones drop to
    two lines before they shrink, and only shrink to ``min_px`` before
    being truncated. A title that would leave a one-word widow on the
    second line stays on one line instead.
    """
    text = " ".join(text.split())
    if not text:
        return "", min_px
    single = avail_px / len(text) / avg
    if max_lines < 2 or single >= max_px * 0.8:
        lines = 1
        font_px = min(max_px, max(min_px, single))
    else:
        lines = 2
        per = -(-len(text) // 2)
        font_px = min(max_px, max(min_px, avail_px / per / avg))
    return _fit_lines(text, _fit_chars(avail_px, font_px, avg), lines), font_px


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
    """A slim rounded progress bar on a neutral track."""
    percent = max(0.0, min(100.0, percent))
    return (
        f'<div style="width: 100%; height: {height_css}; border-radius: 999px; '
        f'background: {track}">'
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
        """Idle / paused / off placeholder — quiet, centered, never loud."""
        if entity is not None and entity.state == "paused":
            icon, label = "pause", "PAUSED"
        else:
            icon, label = "music", "NO MEDIA"
        # A medium glyph in secondary over a tertiary caption: present but
        # recessive, so an idle cell reads as resting rather than broken.
        return (
            '<div class="cell" style="justify-content: center; gap: 3.5vmin">'
            f"{mdi_span(icon, 'icon i-md', 'color: var(--text-secondary)')}"
            f'<div class="t-label hide-short">{escape(label)}</div>'
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
        """Full-bleed album art with a bottom scrim and track info.

        Apple-Music / Spotify now-playing pattern: the art fills the cell,
        the top ~45% stays completely unobstructed, and a gradient scrim
        ramps in below it to carry left-aligned metadata. A hairline
        progress bar sits on the shared bottom inset — never flush to the
        physical edge.

        Overlay text and scrim deliberately use fixed white/black rgba,
        NOT theme tokens: they render over photographic content and need
        the same contrast in every theme. This is the documented
        exception to "use theme tokens for everything".
        """
        if image.mode != "RGB":
            image = image.convert("RGB")
        uri = image_data_uri(image)

        vmin = min(ctx.width, ctx.height)
        avg = _avg_glyph(ctx)
        text_width = ctx.width - 2 * _inset_px(ctx)

        show_artist = self.show_artist and ctx.height >= 120
        show_time = ctx.height >= 190 and duration > 0
        show_bar = self.show_progress and duration > 0

        lines: list[str] = []
        raw_title = entity.get("media_title", "")
        if raw_title:
            title, title_px = _fit_title(
                raw_title,
                text_width,
                avg,
                max_px=_clamp_px(11.0, 0.105, 24.0, vmin),
                max_lines=2 if ctx.height >= 170 else 1,
            )
            lines.append(
                f'<div style="font-size: {title_px:.1f}px; font-weight: 700; '
                'line-height: 1.16; letter-spacing: -0.01em; color: rgba(255,255,255,0.98)">'
                f"{escape(title)}</div>"
            )
        artist = entity.get("media_artist", "")
        if artist and show_artist:
            artist_px = _clamp_px(9.0, 0.072, 15.0, vmin)
            artist = truncate_text(artist, _fit_chars(text_width, artist_px, avg))
            lines.append(
                f'<div style="font-size: {artist_px:.1f}px; font-weight: 600; '
                'line-height: 1.2; color: rgba(255,255,255,0.6); white-space: nowrap">'
                f"{escape(artist)}</div>"
            )
        if show_time:
            time_px = _clamp_px(9.0, 0.055, 12.0, vmin)
            time_str = f"{_format_time(position)} / {_format_time(duration)}"
            lines.append(
                f'<div style="font-size: {time_px:.1f}px; font-weight: 600; '
                'line-height: 1.2; letter-spacing: 0.02em; '
                'color: rgba(255,255,255,0.5); white-space: nowrap">'
                f"{escape(time_str)}</div>"
            )

        text_block = ""
        if lines:
            bottom = (
                f"calc({_INSET} + {_ART_BAR_H} + clamp(4px, 3vmin, 9px))" if show_bar else _INSET
            )
            # Blitz resolves an absolutely positioned box against its
            # *parent* box, so the hide-* wrapper must fill the cell —
            # a zero-height wrapper would collapse the overlay away.
            text_block = (
                '<div class="hide-narrow" style="height: 100%">'
                f'<div style="position: absolute; left: {_INSET}; right: {_INSET}; '
                f"bottom: {bottom}; display: flex; flex-direction: column; "
                'align-items: flex-start; gap: 0.2em; text-align: left">'
                f"{''.join(lines)}</div></div>"
            )

        bar = ""
        if show_bar:
            percent = min(100.0, position / duration * 100)
            bar = (
                f'<div style="position: absolute; left: {_INSET}; right: {_INSET}; '
                f"bottom: {_INSET}; height: {_ART_BAR_H}; border-radius: 999px; "
                'background: rgba(255,255,255,0.28)">'
                f'<div style="width: {percent:.1f}%; height: 100%; border-radius: 999px; '
                f'background: {accent}"></div></div>'
            )

        # Scrim curve: imperceptible through the top 45% of the art, then
        # ramping hard enough that white 700-weight text clears a blown-out
        # highlight in the artwork underneath.
        return (
            '<div style="position: relative; width: 100%; height: 100%; '
            'overflow: hidden; border-radius: inherit">'
            f'<img src="{uri}" style="position: absolute; inset: 0; width: 100%; '
            'height: 100%; object-fit: cover">'
            '<div style="position: absolute; left: 0; right: 0; bottom: 0; height: 60%; '
            "background: linear-gradient(to bottom, rgba(0,0,0,0) 0%, "
            "rgba(0,0,0,0.10) 28%, rgba(0,0,0,0.38) 44%, rgba(0,0,0,0.66) 60%, "
            'rgba(0,0,0,0.80) 80%, rgba(0,0,0,0.92) 100%)"></div>'
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
        avg = _avg_glyph(ctx)
        text_width = ctx.width * 0.88  # 6% padding each side

        bands: list[str] = ['<div class="t-label hide-short">NOW PLAYING</div>']

        title, title_px = _fit_title(
            entity.get("media_title", "Unknown"),
            text_width,
            avg,
            max_px=_clamp_px(13.0, 0.20, 40.0, vmin),
            max_lines=2 if ctx.height >= 90 else 1,
        )
        bands.append(
            f'<div style="font-size: {title_px:.1f}px; font-weight: 700; '
            'line-height: 1.14; letter-spacing: -0.015em">'
            f"{escape(title)}</div>"
        )

        artist = entity.get("media_artist", "")
        if self.show_artist and artist:
            artist_px = _clamp_px(10.0, 0.10, 18.0, vmin)
            artist = truncate_text(artist, _fit_chars(text_width, artist_px, avg))
            bands.append(
                f'<div class="hide-short" style="font-size: {artist_px:.1f}px; '
                "font-weight: 600; line-height: 1.2; color: var(--text-secondary); "
                f'white-space: nowrap">{escape(artist)}</div>'
            )

        album = entity.get("media_album_name", "")
        if self.show_album and album:
            album_px = _clamp_px(9.0, 0.085, 14.0, vmin)
            album = truncate_text(album, _fit_chars(text_width, album_px, avg))
            bands.append(
                f'<div class="hide-small" style="font-size: {album_px:.1f}px; '
                "font-weight: 600; line-height: 1.2; color: var(--text-tertiary); "
                f'white-space: nowrap">{escape(album)}</div>'
            )

        if self.show_progress and duration > 0:
            percent = min(100.0, position / duration * 100)
            bands.append(
                '<div style="width: 100%">'
                + _progress_bar_html(
                    percent,
                    accent,
                    height_css="clamp(3px, 2vmin, 5px)",
                    track="var(--track)",
                )
                # hide-short must sit on an element without an inline
                # display (inline style would beat the media query).
                + '<div class="hide-short">'
                '<div style="display: flex; justify-content: space-between; '
                "color: var(--text-secondary); font-size: clamp(9px, 6.5vmin, 12px); "
                'font-weight: 600; letter-spacing: 0.02em; margin-top: clamp(4px, 2.5vmin, 8px)">'
                f"<span>{escape(_format_time(position))}</span>"
                f"<span>{escape(_format_time(duration))}</span>"
                "</div></div></div>"
            )

        return f'<div class="cell" style="padding: 5% 6%">{"".join(bands)}</div>'
