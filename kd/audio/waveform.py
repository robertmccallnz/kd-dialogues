"""
Render a cream-paper waveform PNG for an episode MP3.

Uses ffmpeg to extract PCM samples, downsamples to N columns, then draws a
symmetric waveform with Pillow. The look matches the six-thinkers site: cream
paper (#f5ecd8), ink (#1c1816), ochre accent (#b0762c).
"""

from __future__ import annotations
import subprocess, struct, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PAPER = (245, 236, 216)
INK   = (28,  24,  22)
OCHRE = (176, 118, 44)
BRICK = (150, 60, 40)

WIDTH  = 1600
HEIGHT = 900
PADDING_X = 80
PADDING_Y_TOP = 130
PADDING_Y_BOTTOM = 130
BAR_WIDTH = 4
BAR_GAP   = 2

FONT_BOLD  = "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf"
FONT_REG   = "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"
FONT_ITAL  = "/usr/share/fonts/truetype/noto/NotoSerif-Italic.ttf"


def _load_samples(mp3: Path, target_columns: int) -> list[float]:
    """Decode the mp3 to mono 22.05kHz s16le and reduce to per-column peak amplitude."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3),
         "-ac", "1", "-ar", "22050", "-f", "s16le", "-"],
        check=True, capture_output=True,
    )
    raw = proc.stdout
    n_samples = len(raw) // 2
    if n_samples == 0:
        return [0.0] * target_columns
    samples_per_col = max(1, n_samples // target_columns)

    peaks: list[float] = []
    for col in range(target_columns):
        start = col * samples_per_col * 2
        end   = min(len(raw), start + samples_per_col * 2)
        if start >= end:
            peaks.append(0.0)
            continue
        chunk = raw[start:end]
        # unpack a stride of samples to keep this fast
        stride = max(1, len(chunk) // (2 * 128))
        max_amp = 0
        for i in range(0, len(chunk), 2 * stride):
            (v,) = struct.unpack_from("<h", chunk, i)
            v = abs(v)
            if v > max_amp:
                max_amp = v
        peaks.append(max_amp / 32768.0)
    # Small smoothing pass so the bars aren't jagged noise
    smoothed = peaks[:]
    for i in range(1, len(peaks) - 1):
        smoothed[i] = (peaks[i-1] + 2*peaks[i] + peaks[i+1]) / 4
    return smoothed


def render(mp3: Path, out_png: Path, *, title: str, subtitle: str, cast: list[str]) -> Path:
    inner_w = WIDTH - 2 * PADDING_X
    inner_h = HEIGHT - PADDING_Y_TOP - PADDING_Y_BOTTOM
    columns = inner_w // (BAR_WIDTH + BAR_GAP)

    peaks = _load_samples(mp3, columns)
    max_peak = max(peaks) or 1.0
    peaks = [p / max_peak for p in peaks]

    img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    d = ImageDraw.Draw(img)

    # Fine tooth border, like a torn-paper edge
    for y_off in range(4):
        d.line([(PADDING_X - 6, PADDING_Y_TOP + 8 * y_off),
                (WIDTH - PADDING_X + 6, PADDING_Y_TOP + 8 * y_off)],
               fill=OCHRE if y_off == 0 else PAPER, width=1)

    # Centre baseline
    cy = PADDING_Y_TOP + inner_h // 2

    # Waveform bars — ink for the body, ochre accent at every 24th bar for rhythm
    for i, p in enumerate(peaks):
        x = PADDING_X + i * (BAR_WIDTH + BAR_GAP)
        h = int(p * (inner_h / 2) * 0.92) + 2
        colour = OCHRE if (i % 24 == 0 and p > 0.15) else INK
        d.rectangle([x, cy - h, x + BAR_WIDTH, cy + h], fill=colour)

    # Faint centre line under the bars
    d.line([(PADDING_X, cy), (WIDTH - PADDING_X, cy)], fill=OCHRE, width=1)

    # Title block
    try:
        title_font = ImageFont.truetype(FONT_BOLD, 46)
        sub_font   = ImageFont.truetype(FONT_ITAL, 26)
        cast_font  = ImageFont.truetype(FONT_REG, 22)
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = cast_font = title_font

    # Wrap the title to two lines if it's long
    title = title.strip() or "Untitled episode"
    max_chars = 40
    title_lines: list[str] = []
    if len(title) <= max_chars:
        title_lines = [title]
    else:
        # split at nearest space to the middle
        words = title.split()
        line, lines = "", []
        for w in words:
            probe = f"{line} {w}".strip()
            if len(probe) > max_chars and line:
                lines.append(line); line = w
            else:
                line = probe
        if line: lines.append(line)
        title_lines = lines[:2]

    y = 46
    for tl in title_lines:
        d.text((PADDING_X, y), tl, fill=INK, font=title_font)
        y += 52

    if subtitle:
        d.text((PADDING_X, y), subtitle.strip(), fill=BRICK, font=sub_font)

    if cast:
        cast_str = " · ".join(c.title() for c in cast)
        d.text((PADDING_X, HEIGHT - PADDING_Y_BOTTOM + 55), cast_str, fill=INK, font=cast_font)

    # Bottom-right corner mark
    mark = "kd-dialogues"
    try:
        mark_font = ImageFont.truetype(FONT_ITAL, 18)
    except Exception:
        mark_font = cast_font
    tw = d.textlength(mark, font=mark_font)
    d.text((WIDTH - PADDING_X - tw, HEIGHT - PADDING_Y_BOTTOM + 58),
           mark, fill=OCHRE, font=mark_font)

    img.save(out_png, "PNG", optimize=True)
    return out_png


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("mp3", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default="Untitled")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--cast", nargs="*", default=[])
    args = ap.parse_args()
    render(args.mp3, args.out, title=args.title, subtitle=args.subtitle, cast=args.cast)
    print(f"wrote {args.out}")
