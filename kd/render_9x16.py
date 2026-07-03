"""9:16 (1080×1920) vertical renderer — TikTok / Reels / Shorts."""

from __future__ import annotations
import shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw
from .render_common import (
    CREAM, INK, OCHRE, RED_BROWN, FONT_TITLE, FONT_BODY, FONT_ITAL,
    font, build_paper, build_portrait_cache, wrap_lines,
    build_timeline, frame_kind_at, beat_alphas, probe_duration,
)

W, H = 1080, 1920
FPS = 24
PORTRAIT_H = 460


def positions(n: int) -> list[tuple[int, int]]:
    COL_L = int(W * 0.28)
    COL_R = int(W * 0.72)
    ROW_Y = [int(H * 0.14), int(H * 0.36), int(H * 0.58)]
    if n == 6:
        return [
            (COL_L, ROW_Y[0]), (COL_R, ROW_Y[0]),
            (COL_R, ROW_Y[1]), (COL_L, ROW_Y[2]),
            (COL_R, ROW_Y[2]), (COL_L, ROW_Y[1]),
        ]
    # generic column layout for other counts
    cols = 2
    rows = (n + cols - 1) // cols
    xs = [int(W * (0.28 + 0.44 * (i % cols))) for i in range(n)]
    ys = [int(H * (0.12 + 0.48 * ((i // cols) / max(1, rows - 1)))) for i in range(n)]
    return list(zip(xs, ys))


def draw_caption(canvas, name, quote, alpha):
    if alpha <= 0: return
    d = ImageDraw.Draw(canvas, "RGBA")
    top = int(H * 0.80)
    panel = Image.new("RGBA", (W, H - top), (30, 26, 22, int(alpha * 0.78)))
    canvas.paste(panel, (0, top), panel)
    nf = font(FONT_TITLE, 56)
    bf = font(FONT_ITAL, 44)
    d.text((60, top+30), name, font=nf, fill=(240,232,210,alpha))
    d.rectangle([60, top+100, 240, top+104], fill=(*OCHRE, alpha))
    lines = wrap_lines(quote, bf, W-120)
    y = top + 130
    for line in lines[:4]:
        d.text((60, y), line, font=bf, fill=(245,236,216,alpha))
        y += 54


def render(script, audio_dir: Path, thinkers_root: Path, out_dir: Path) -> Path:
    slug = script["slug"]
    thinkers = script["_thinkers"]
    n = len(thinkers)
    pos = positions(n)
    paper = build_paper((W, H))
    pcache = build_portrait_cache(thinkers, thinkers_root, PORTRAIT_H)

    beat_durs = [probe_duration(audio_dir / f"{t['slug']}.mp3") for t in thinkers]
    timeline, beats, total = build_timeline(
        cold=3.0, tail=0.6, beat_durations=beat_durs, turn=3.0, end=3.0
    )
    n_frames = int(total * FPS)

    frames_dir = out_dir / "_frames_9x16"
    if frames_dir.exists(): shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    for fi in range(n_frames):
        t = fi / FPS
        s, e, idx, kind = frame_kind_at(t, timeline)
        local = (t - s) / max(1e-6, e - s)

        if kind == "cold":
            img = paper.copy()
            d = ImageDraw.Draw(img, "RGBA")
            a = (int(255*local/0.4) if local<0.4
                 else 255 if local<0.7
                 else int(255*(1-(local-0.7)/0.3)))
            f_ = font(FONT_ITAL, 58)
            # wrap for narrow frame
            text = script.get("cold_open", "")
            lines = wrap_lines(text, f_, W - 100)
            y = int(H * 0.42)
            for line in lines:
                bb = f_.getbbox(line); tw = bb[2]-bb[0]
                d.text(((W-tw)//2, y), line, font=f_, fill=(*INK, a))
                y += 80

        elif kind == "beat":
            aa = beat_alphas(t, s, e)
            img = paper.copy()
            for i, th in enumerate(thinkers):
                pim, m = pcache[th["slug"]]["idle"]
                img.paste(pim, (pos[i][0]-pim.width//2, pos[i][1]-pim.height//2), m)
            if 0 <= idx < n and aa > 0:
                sa = thinkers[idx]["slug"]
                act, am = pcache[sa]["active"]
                img.paste(act, (pos[idx][0]-act.width//2, pos[idx][1]-act.height//2),
                          am.point(lambda v: int(v * aa)))
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
                lines = wrap_lines(text, f_, W-80)
                d.rectangle([0, int(H*0.83), W, H], fill=(28,24,22,int(a*0.85)))
                y = int(H * 0.85)
                for line in lines:
                    bb = f_.getbbox(line); tw = bb[2]-bb[0]
                    d.text(((W-tw)//2, y), line, font=f_, fill=(245,236,216,a))
                    y += 80

        else:  # end
            img = paper.copy()
            d = ImageDraw.Draw(img, "RGBA")
            f_h1 = font(FONT_TITLE, 72)
            f_h2 = font(FONT_BODY, 38)
            f_url = font(FONT_ITAL, 32)
            a = int(255 * min(1, local/0.4))
            end = script.get("end_card", {})
            title_lines = wrap_lines(script.get("title",""), f_h1, W-80)
            y = int(H*0.30)
            for line in title_lines:
                bb = f_h1.getbbox(line); tw = bb[2]-bb[0]
                d.text(((W-tw)//2, y), line, font=f_h1, fill=(*INK, a))
                y += 90
            d.rectangle([W//2-150, y+10, W//2+150, y+14], fill=(*OCHRE, a))
            y += 60
            for text, f_, col in [
                (script.get("subtitle",""), f_h2, INK),
                (end.get("line_1",""),      f_h2, OCHRE),
                (end.get("url_1",""),       f_url, INK),
                (end.get("url_2",""),       f_url, INK),
            ]:
                if not text: continue
                for line in wrap_lines(text, f_, W-80):
                    bb = f_.getbbox(line); tw = bb[2]-bb[0]
                    d.text(((W-tw)//2, y), line, font=f_, fill=(*col, a))
                    y += 55

        img.save(frames_dir / f"f{fi:05d}.png", "PNG", compress_level=1)
        if fi % 200 == 0:
            print(f"  9:16  {fi}/{n_frames}  t={t:.1f}s  ({kind})")

    out_mp4 = out_dir / f"{slug}-9x16.mp4"
    audio_mix = out_dir / "audio_mix.m4a"
    subprocess.check_call([
        "ffmpeg","-y","-framerate", str(FPS), "-i", f"{frames_dir}/f%05d.png",
        "-i", str(audio_mix),
        "-c:v","libx264","-pix_fmt","yuv420p","-crf","18","-preset","medium",
        "-c:a","aac","-b:a","192k","-shortest", str(out_mp4),
    ])
    return out_mp4
