"""
Shared render primitives for the kd-dialogues engine.

The three renderers (render_16x9, render_9x16, render_1x1) all use the same
paper/portrait/caption primitives from this module — only the canvas size and
the portrait grid layout change.
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

# --- design tokens ---
CREAM     = (245, 236, 216)
INK       = (28, 24, 22)
OCHRE     = (176, 118, 44)
RED_BROWN = (150, 60, 40)

FONT_TITLE = "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf"
FONT_BODY  = "/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"
FONT_ITAL  = "/usr/share/fonts/truetype/noto/NotoSerif-Italic.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def probe_duration(mp3_path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_path),
    ])
    return float(out.strip())


def desaturate(im: Image.Image, amount: float) -> Image.Image:
    return ImageEnhance.Color(im).enhance(1 - amount)


def warm(im: Image.Image, amount: float) -> Image.Image:
    r, g, b = im.split()
    r = r.point(lambda v: min(255, int(v * (1 + amount * 0.12))))
    b = b.point(lambda v: max(0, int(v * (1 - amount * 0.10))))
    return Image.merge("RGB", (r, g, b))


def build_paper(size: tuple[int, int]) -> Image.Image:
    """Cream paper with subtle ochre vignette in the four corners."""
    w, h = size
    bg = Image.new("RGB", size, CREAM)
    overlay = Image.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for corner in [(0, 0), (w, 0), (0, h), (w, h)]:
        for r in range(300, 0, -60):
            alpha = int(20 - r / 16)
            if alpha <= 0:
                continue
            d.ellipse([corner[0]-r, corner[1]-r, corner[0]+r, corner[1]+r], fill=OCHRE)
    return Image.blend(bg, overlay, 0.06)


def prep_portrait(portrait_path: Path, target_h: int) -> Image.Image:
    im = Image.open(portrait_path).convert("RGB")
    ratio = target_h / im.height
    return im.resize((int(im.width * ratio), target_h), Image.LANCZOS)


def mask_for(pim: Image.Image, blur: int = 18) -> Image.Image:
    m = Image.new("L", pim.size, 0)
    ImageDraw.Draw(m).rectangle([0, 0, pim.width, pim.height], fill=255)
    return m.filter(ImageFilter.GaussianBlur(radius=blur))


def build_portrait_cache(thinkers: list[dict], thinkers_root: Path, portrait_h: int) -> dict:
    """
    thinkers: list of dicts with at least a 'slug' key.
    Returns {slug: {'idle': (im, mask), 'active': (im, mask)}} for O(1) lookup at frame time.
    """
    cache: dict[str, dict] = {}
    for t in thinkers:
        slug = t["slug"]
        base = prep_portrait(thinkers_root / slug / "portrait.png", portrait_h)
        idle = ImageEnhance.Brightness(desaturate(base, 0.75)).enhance(0.75)
        active = base.resize(
            (int(base.width * 1.15), int(base.height * 1.15)), Image.LANCZOS
        )
        active = ImageEnhance.Brightness(warm(active, 1.0)).enhance(1.05)
        cache[slug] = {
            "idle": (idle, mask_for(idle)),
            "active": (active, mask_for(active)),
        }
    return cache


def wrap_lines(text: str, font_obj, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            trial = (cur + " " + w).strip()
            if font_obj.getbbox(trial)[2] <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def build_timeline(cold: float, tail: float, beat_durations: list[float],
                   turn: float, end: float) -> tuple[list, list, float]:
    """
    Returns (timeline, beats, total_seconds).
    timeline entries: (start, end, active_idx, kind)
      kind ∈ {'cold', 'beat', 'turn', 'end'}
    beats: (start, end, idx, thinker_slug)  — used later for audio placement
    """
    timeline: list = []
    beats: list = []
    cursor = 0.0
    timeline.append((0.0, cold, -1, "cold"))
    cursor = cold
    for i, dur in enumerate(beat_durations):
        beat_dur = dur + tail
        beats.append((cursor, cursor + beat_dur, i, None))
        timeline.append((cursor, cursor + beat_dur, i, "beat"))
        cursor += beat_dur
    timeline.append((cursor, cursor + turn, -1, "turn"))
    cursor += turn
    timeline.append((cursor, cursor + end, -1, "end"))
    cursor += end
    return timeline, beats, cursor


def frame_kind_at(t: float, timeline: list):
    for s, e, idx, kind in timeline:
        if s <= t < e:
            return s, e, idx, kind
    return timeline[-1]


def beat_alphas(t: float, s: float, e: float,
                fade_in: float = 0.35, tail: float = 0.6) -> float:
    """Active-alpha for the speaker portrait / caption during a beat."""
    if t - s < fade_in:
        return (t - s) / fade_in
    if e - t < tail:
        return max(0.0, (e - t) / tail)
    return 1.0
