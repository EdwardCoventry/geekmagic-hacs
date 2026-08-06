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
# mixed-case strings in the two embedded families, plus a ~10% safety
# margin: Nunito ~0.452, DejaVu Sans ~0.551. Being slightly pessimistic
# guarantees the engine always fits at least as much as we assumed, so a
# block never grows an unplanned extra line.
#
# _CHROME_PX covers the padding+border themes paint on ``.root``
# (retro/minimal 5px, light 6px, watchOS 0). That inset shrinks the
# fragment below ``ctx.width``, and it lives inside ``theme.chrome_css``
# where widgets can't read it — so reserve the worst case.
# ---------------------------------------------------------------------------
_AVG_ROUNDED = 0.50
_AVG_WIDE = 0.62
_CHROME_PX = 6.0

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


def _fit_lines(text: str, per_line: int, max_lines: int) -> tuple[str, int]:
    """Greedy-wrap ``text`` and hard-truncate it to ``max_lines`` lines.

    Returns the fitted string (the engine re-wraps it at the same budget)
    and the number of lines it will occupy. Because ``per_line`` comes
    from a pessimistic glyph advance, the rendered block never overflows
    the line count reported here.
    """
    words = text.split()
    if not words:
        return "", 0
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
    return " ".join(lines), len(lines)


def _fit_title(
    text: str,
    avail_px: float,
    avg: float,
    *,
    max_px: float,
    max_lines: int,
    min_px: float = 11.0,
) -> tuple[str, float, int]:
    """Pick a font size and wrap/truncate a title to fill ``avail_px``.

    Short titles grow to ``max_px`` (hero dominance); long ones drop to
    two lines before they shrink, and only shrink to ``min_px`` before
    being truncated. A title that would leave a one-word widow on the
    second line stays on one line instead. Returns the fitted text, its
    font size in px, and the number of lines it occupies.
    """
    text = " ".join(text.split())
    if not text:
        return "", min_px, 0
    single = avail_px / len(text) / avg
    if max_lines < 2 or single >= max_px * 0.8:
        allowed = 1
        font_px = min(max_px, max(min_px, single))
    else:
        allowed = 2
        per = -(-len(text) // 2)
        font_px = min(max_px, max(min_px, avail_px / per / avg))
    fitted, lines = _fit_lines(text, _fit_chars(avail_px, font_px, avg), allowed)
    return fitted, font_px, lines


def _art_scrim(cell_h: int, block_px: float) -> str:
    """Gradient scrim for the album-art overlay, sized to its text block.

    The scrim is anchored to the bottom and its ramp is derived from where
    the metadata actually starts, so the overlay carries the same contrast
    whether it holds one line or four. Two guarantees fall out of the
    stop positions: the top of the cover is never touched (the scrim
    starts at 42% at the very earliest, and is under 6% opaque for the
    first stretch of its own height), and the text always sits on ~46%
    black or deeper.
    """
    text_top = 1.0 - block_px / max(1, cell_h)
    start = min(0.62, max(0.42, text_top - 0.11))
    p_text = min(0.9, max(0.12, (text_top - start) / (1.0 - start)))
    stops = (
        (0.0, 0.0),
        (p_text * 0.45, 0.06),
        (p_text, 0.46),
        (p_text + (1.0 - p_text) * 0.35, 0.70),
        (1.0, 0.94),
    )
    ramp = ", ".join(f"rgba(0,0,0,{a:.2f}) {p * 100:.0f}%" for p, a in stops)
    return (
        '<div style="position: absolute; left: 0; right: 0; bottom: 0; '
        f'height: {(1.0 - start) * 100:.0f}%; '
        f'background: linear-gradient(to bottom, {ramp})"></div>'
    )


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
        text_width = ctx.width - 2 * _inset_px(ctx) - _CHROME_PX

        show_bar = self.show_progress and duration > 0
        # Height budget, in px, of everything stacked above the bottom
        # inset — it drives where the scrim has to start.
        gap_px = 0.2 * _clamp_px(11.0, 0.105, 24.0, vmin)
        block_px = 0.0

        lines: list[str] = []
        raw_title = entity.get("media_title", "")
        title_lines = 0
        if raw_title:
            title, title_px, title_lines = _fit_title(
                raw_title,
                text_width,
                avg,
                max_px=_clamp_px(11.0, 0.105, 24.0, vmin),
                max_lines=2 if ctx.height >= 170 else 1,
            )
            block_px += title_lines * title_px * 1.16
            lines.append(
                f'<div style="font-size: {title_px:.1f}px; font-weight: 700; '
                'line-height: 1.16; letter-spacing: -0.01em; color: rgba(255,255,255,0.98)">'
                f"{escape(title)}</div>"
            )
        artist = entity.get("media_artist", "")
        if artist and self.show_artist and ctx.height >= 120:
            artist_px = _clamp_px(9.0, 0.072, 15.0, vmin)
            artist = truncate_text(artist, _fit_chars(text_width, artist_px, avg))
            block_px += artist_px * 1.2 + gap_px
            lines.append(
                f'<div style="font-size: {artist_px:.1f}px; font-weight: 600; '
                'line-height: 1.2; color: rgba(255,255,255,0.6); white-space: nowrap">'
                f"{escape(artist)}</div>"
            )
        # The bar already shows elapsed position graphically, so the
        # numeric readout only earns its place when the title is a single
        # line and there is real room left.
        if duration > 0 and ctx.height >= 190 and title_lines <= 1:
            time_px = _clamp_px(9.0, 0.055, 12.0, vmin)
            time_str = f"{_format_time(position)} / {_format_time(duration)}"
            block_px += time_px * 1.2 + gap_px
            lines.append(
                f'<div style="font-size: {time_px:.1f}px; font-weight: 600; '
                'line-height: 1.2; letter-spacing: 0.02em; '
                'color: rgba(255,255,255,0.5); white-space: nowrap">'
                f"{escape(time_str)}</div>"
            )

        bar_zone = _inset_px(ctx) + (_clamp_px(2.0, 0.014, 4.0, vmin) + 6.0 if show_bar else 0.0)
        if ctx.width < 100:
            block_px = 0.0  # .hide-narrow drops the text block entirely

        text_block = ""
        if lines:
            bottom = (
                f"calc({_INSET} + {_ART_BAR_H} + clamp(4px, 3vmin, 9px))" if show_bar else _INSET
            )
            # Two engine constraints shape this wrapper: Blitz resolves an
            # absolutely positioned box against its *parent* box (a
            # zero-height wrapper would collapse the overlay away), and it
            # paints non-positioned subtrees before positioned siblings (a
            # static wrapper would put the text UNDER the scrim). So the
            # hide-* wrapper is itself absolute and fills the cell.
            text_block = (
                '<div class="hide-narrow" style="position: absolute; inset: 0">'
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

        # ``border-radius: inherit`` picks up the theme's card rounding
        # (light/classic/soft) and stays square on the chromeless themes.
        return (
            '<div style="position: relative; width: 100%; height: 100%; '
            'overflow: hidden; border-radius: inherit">'
            f'<img src="{uri}" style="position: absolute; inset: 0; width: 100%; '
            'height: 100%; object-fit: cover">'
            f"{_art_scrim(ctx.height, block_px + bar_zone)}"
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
        text_width = ctx.width * 0.88 - _CHROME_PX  # 6% padding each side

        bands: list[str] = ['<div class="t-label hide-short">NOW PLAYING</div>']

        title, title_px, _ = _fit_title(
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
