"""16:9 (1920×1080) horizontal renderer — YouTube / Vimeo master."""

from __future__ import annotations
import shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw
from .render_common import (
    CREAM, INK, OCHRE, RED_BROWN, FONT_TITLE, FONT_BODY, FONT_ITAL,
    font, build_paper, build_portrait_cache, wrap_lines,
    build_timeline, frame_kind_at, beat_alphas, probe_duration,
)

W, H = 1920, 1080
FPS = 24
PORTRAIT_H = int(H * 0.34)


def positions(n: int) -> list[tuple[int, int]]:
    """
    Manual hex-ish layout for six thinkers.
    Extending to n > 6 falls back to an even-spaced ring.
    """
    if n == 6:
        return [
            (W // 2,        int(H * 0.24)),
            (int(W * 0.82), int(H * 0.30)),
            (int(W * 0.82), int(H * 0.60)),
            (W // 2,        int(H * 0.66)),
            (int(W * 0.18), int(H * 0.60)),
            (int(W * 0.18), int(H * 0.30)),
        ]
    # generic ring fallback
    import math
    cx, cy = W // 2, int(H * 0.45)
    rx, ry = int(W * 0.32), int(H * 0.24)
    return [
        (int(cx + rx * math.cos(2*math.pi*i/n - math.pi/2)),
         int(cy + ry * math.sin(2*math.pi*i/n - math.pi/2)))
        for i in range(n)
    ]


def draw_caption(canvas, name, quote, alpha):
    if alpha <= 0:
        return
    d = ImageDraw.Draw(canvas, "RGBA")
    top = int(H * 0.80)
    panel = Image.new("RGBA", (W, H - top), (30, 26, 22, int(alpha * 0.78)))
    canvas.paste(panel, (0, top), panel)
    nf = font(FONT_TITLE, 44)
    bf = font(FONT_ITAL, 44)
    d.text((80, top + 20), name, font=nf, fill=(240, 232, 210, alpha))
    d.rectangle([80, top + 78, 260, top + 82], fill=(*OCHRE, alpha))
    lines = wrap_lines(quote, bf, W - 160)
    y = top + 100
    for line in lines[:3]:
        d.text((80, y), line, font=bf, fill=(245, 236, 216, alpha))
        y += 54


def render(script: dict, audio_dir: Path, thinkers_root: Path, out_dir: Path) -> Path:
    """Render 16:9 promo to out_dir/{slug}-16x9.mp4. Returns the mp4 path."""
    slug = script["slug"]
    thinkers = script["_thinkers"]  # already-materialised thinker dicts (see generate.py)
    n = len(thinkers)
    pos = positions(n)

    paper = build_paper((W, H))
    pcache = build_portrait_cache(thinkers, thinkers_root, PORTRAIT_H)

    # timing
    beat_durs = [probe_duration(audio_dir / f"{t['slug']}.mp3") for t in thinkers]
    timeline, beats, total = build_timeline(
        cold=3.0, tail=0.6, beat_durations=beat_durs, turn=3.0, end=3.0
    )
    n_frames = int(total * FPS)

    frames_dir = out_dir / "_frames_16x9"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    for fi in range(n_frames):
        t = fi / FPS
        s, e, idx, kind = frame_kind_at(t, timeline)
        local = (t - s) / max(1e-6, (e - s))

        if kind == "cold":
            img = paper.copy()
            d = ImageDraw.Draw(img, "RGBA")
            a = (int(255*local/0.4) if local<0.4
                 else 255 if local<0.7
                 else int(255*(1-(local-0.7)/0.3)))
            f_ = font(FONT_ITAL, 78)
            text = script.get("cold_open", "")
            bb = f_.getbbox(text); tw = bb[2]-bb[0]
            d.text(((W-tw)//2, int(H*0.44)), text, font=f_,
                   fill=(*INK, a))

        elif kind == "beat":
            aa = beat_alphas(t, s, e)
            img = paper.copy()
            for i, th in enumerate(thinkers):
                pim, m = pcache[th["slug"]]["idle"]
                img.paste(pim, (pos[i][0]-pim.width//2, pos[i][1]-pim.height//2), m)
            if 0 <= idx < n and aa > 0:
                slug_a = thinkers[idx]["slug"]
                act, am = pcache[slug_a]["active"]
                alpha_mask = am.point(lambda v: int(v * aa))
                img.paste(act, (pos[idx][0]-act.width//2, pos[idx][1]-act.height//2),
                          alpha_mask)
                draw_caption(img, thinkers[idx]["display_name"],
                             thinkers[idx]["caption"], int(255*aa))

        elif kind == "turn":
            img = paper.copy()
            wh = int(H*0.4*local)
            if wh > 0:
                wash = Image.new("RGBA",(W,wh),(*RED_BROWN,40))
                img.paste(wash, (0, H-wh), wash)
            for i, th in enumerate(thinkers):
                act, am = pcache[th["slug"]]["active"]
                img.paste(act, (pos[i][0]-act.width//2, pos[i][1]-act.height//2), am)
            d = ImageDraw.Draw(img, "RGBA")
            if local > 0.25:
                a = int(255*min(1,(local-0.25)/0.35))
                f_ = font(FONT_ITAL, 62)
                text = script.get("turn_card", "Now — your turn.")
                bb = f_.getbbox(text); tw = bb[2]-bb[0]
                d.rectangle([0,int(H*0.85),W,H], fill=(28,24,22,int(a*0.8)))
                d.text(((W-tw)//2, int(H*0.87)), text, font=f_, fill=(245,236,216,a))

        else:  # end
            img = paper.copy()
            d = ImageDraw.Draw(img, "RGBA")
            f_h1 = font(FONT_TITLE, 92)
            f_h2 = font(FONT_BODY, 44)
            f_url = font(FONT_ITAL, 40)
            a = int(255*min(1, local/0.4))
            end = script.get("end_card", {})
            title = script.get("title", "")
            sub = script.get("subtitle", "")
            line3 = end.get("line_1", "")
            url = " · ".join(x for x in [end.get("url_1"), end.get("url_2")] if x)
            for text, f_, y, col in [
                (title, f_h1, int(H*0.34), INK),
                (sub,   f_h2, int(H*0.50), INK),
                (line3, f_h2, int(H*0.58), OCHRE),
                (url,   f_url, int(H*0.72), INK),
            ]:
                if not text: continue
                bb = f_.getbbox(text); tw = bb[2]-bb[0]
                d.text(((W-tw)//2, y), text, font=f_, fill=(*col, a))
            d.rectangle([W//2-200, int(H*0.44), W//2+200, int(H*0.44)+4],
                        fill=(*OCHRE, a))

        img.save(frames_dir / f"f{fi:05d}.png", "PNG", compress_level=1)
        if fi % 200 == 0:
            print(f"  16:9  {fi}/{n_frames}  t={t:.1f}s  ({kind})")

    # encode with the mixed audio (built separately in generate.py)
    out_mp4 = out_dir / f"{slug}-16x9.mp4"
    audio_mix = out_dir / "audio_mix.m4a"
    subprocess.check_call([
        "ffmpeg","-y","-framerate", str(FPS), "-i", f"{frames_dir}/f%05d.png",
        "-i", str(audio_mix),
        "-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-preset","medium",
        "-c:a","aac","-b:a","192k","-shortest", str(out_mp4),
    ])
    return out_mp4
