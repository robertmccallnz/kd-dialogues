"""
kd-dialogues main entrypoint.

Usage:
    python -m kd.generate dialogues/001-first-round/script.yml

This does the whole pipeline for a single dialogue:
  1. Load script.yml + resolve each line's thinker profile (voice.yml)
  2. Synthesise each line (asi-text-to-speech) → audio/<slug>.mp3
  3. Build the mixed audio track (audio_mix.m4a)
  4. Render 16:9, 9:16, and 1:1 videos into dialogue/video/
  5. Emit a Substack embed snippet + metadata sidecar

To publish afterwards, run publish.py (see README).
"""

from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import yaml

from .render_common import probe_duration
from .tts import synth_line, build_audio_mix
from .render_16x9 import render as render_16x9
from .render_9x16 import render as render_9x16
from .render_1x1 import render as render_1x1


REPO_ROOT = Path(__file__).resolve().parent.parent
THINKERS_ROOT = REPO_ROOT / "thinkers"


def load_thinker(slug: str) -> dict:
    """Load thinkers/<slug>/voice.yml and validate portrait.png exists."""
    tdir = THINKERS_ROOT / slug
    voice_path = tdir / "voice.yml"
    portrait_path = tdir / "portrait.png"
    if not voice_path.exists():
        raise FileNotFoundError(f"Missing thinker profile: {voice_path}")
    if not portrait_path.exists():
        raise FileNotFoundError(f"Missing portrait: {portrait_path}")
    data = yaml.safe_load(voice_path.read_text())
    data["slug"] = slug
    data["portrait_path"] = portrait_path
    return data


def resolve_script(script_path: Path) -> dict:
    """Load script.yml and materialise each line's thinker + caption fallbacks."""
    script = yaml.safe_load(script_path.read_text())
    thinkers_used: list[dict] = []
    for line in script["lines"]:
        th = load_thinker(line["thinker"])
        # Merge the thinker profile with per-line overrides:
        entry = {
            "slug": th["slug"],
            "display_name": th["display_name"],
            "tts_voice": th["tts_voice"],
            "say": line["say"].strip(),
            "caption": (line.get("caption") or line["say"]).strip(),
        }
        thinkers_used.append(entry)
    script["_thinkers"] = thinkers_used
    return script


def synthesise_all(script: dict, audio_dir: Path) -> list[dict]:
    """
    Synthesise one mp3 per line. Returns a list of beat dicts
    ordered by appearance, each with slug and duration.
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    beats: list[dict] = []
    for t in script["_thinkers"]:
        slug = t["slug"]
        mp3 = audio_dir / f"{slug}.mp3"
        if mp3.exists():
            print(f"  (cached) {slug}.mp3")
        else:
            print(f"  synthesising {slug} with voice={t['tts_voice']}...")
            synth_line(t["say"], t["tts_voice"], mp3)
        beats.append({"slug": slug, "duration": probe_duration(mp3)})
    return beats


def build_beat_timeline(beats: list[dict], cold: float = 3.0, tail: float = 0.6,
                         turn: float = 3.0, end: float = 3.0):
    """Return the list of beat dicts with start/end filled in, plus total runtime."""
    cursor = cold
    for b in beats:
        b["start"] = cursor
        b["end"] = cursor + b["duration"] + tail
        cursor = b["end"]
    total = cursor + turn + end
    return beats, total


def write_embed_snippet(script: dict, out_dir: Path, videos: dict) -> Path:
    """Emit an HTML embed snippet for Substack.

    We prefer the 1:1 mp4 for feed readability, falling back to 16:9 then 9:16.
    The `{{VIDEO_URL}}` token is left in place so the author can point it at
    whatever CDN/repo raw URL they end up hosting the mp4 on (GitHub raw,
    PeerTube, S3, etc.). See publish.py for a helper that fills it in.
    """
    slug = script["slug"]
    preferred = None
    for key in ("1x1", "16x9", "9x16"):
        if key in videos:
            preferred = videos[key].name
            break
    fallback_src = preferred or f"{slug}-1x1.mp4"
    html = f"""<!-- Substack embed for kd-dialogues :: {slug} -->
<!-- Replace the src below with a public URL to the mp4, e.g. a GitHub raw URL. -->
<video controls playsinline preload="metadata" style="width:100%;max-width:640px;background:#f5ecd8">
  <source src="{{VIDEO_URL}}" type="video/mp4" />
  Your browser cannot play the six-thinkers dialogue video.
</video>
<p style="font-family:'Noto Serif',Georgia,serif;color:#1c1816;text-align:center;font-style:italic">
  {script.get("title","")} — {script.get("subtitle","")}
</p>
"""
    p = out_dir / "embed.html"
    p.write_text(html, encoding="utf-8")
    return p


def write_metadata(script: dict, beats: list[dict], out_dir: Path, videos: dict) -> Path:
    """A machine-readable sidecar for the catalogue page + publishers."""
    md = {
        "slug": script["slug"],
        "title": script.get("title"),
        "subtitle": script.get("subtitle"),
        "runtime_seconds": beats[-1]["end"] + 6.0 if beats else 0,
        "thinkers": [t["slug"] for t in script["_thinkers"]],
        "beats": [{"slug": b["slug"], "start": b["start"], "end": b["end"]} for b in beats],
        "videos": {k: str(v.relative_to(out_dir.parent)) for k, v in videos.items()},
    }
    p = out_dir / "metadata.json"
    p.write_text(json.dumps(md, indent=2), encoding="utf-8")
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", type=Path, help="Path to a dialogue script.yml")
    ap.add_argument("--aspects", default="16x9,9x16,1x1",
                    help="Comma-separated aspect ratios to render.")
    ap.add_argument("--skip-tts", action="store_true",
                    help="Skip TTS synthesis (reuse existing audio/*.mp3).")
    args = ap.parse_args()

    script_path = args.script.resolve()
    script = resolve_script(script_path)
    dialogue_dir = script_path.parent
    audio_dir = dialogue_dir / "audio"
    out_dir = dialogue_dir / "video"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Synthesise per-line audio
    if args.skip_tts:
        beats = [{"slug": t["slug"], "duration": probe_duration(audio_dir / f"{t['slug']}.mp3")}
                 for t in script["_thinkers"]]
        print("Skipping TTS synth (cache-only).")
    else:
        beats = synthesise_all(script, audio_dir)

    # 2. Compute beat timeline
    beats, total = build_beat_timeline(beats)
    print(f"\nTotal runtime: {total:.2f}s across {len(beats)} beats")

    # 3. Mix audio
    audio_mix = out_dir / "audio_mix.m4a"
    build_audio_mix(beats, audio_dir, total, audio_mix)
    print(f"Mixed audio → {audio_mix}")

    # 4. Render each aspect ratio
    aspects = args.aspects.split(",")
    videos: dict[str, Path] = {}
    if "16x9" in aspects:
        print("\nRendering 16:9 master...")
        videos["16x9"] = render_16x9(script, audio_dir, THINKERS_ROOT, out_dir)
    if "9x16" in aspects:
        print("\nRendering 9:16 vertical...")
        videos["9x16"] = render_9x16(script, audio_dir, THINKERS_ROOT, out_dir)
    if "1x1" in aspects:
        print("\nRendering 1:1 square...")
        videos["1x1"] = render_1x1(script, audio_dir, THINKERS_ROOT, out_dir)

    # 5. Emit sidecars — merge with any videos that already exist on disk
    # so partial runs (--aspects 16x9 then --aspects 9x16) still yield a
    # complete metadata sidecar.
    for asp in ("16x9", "9x16", "1x1"):
        candidate = out_dir / f"{script['slug']}-{asp}.mp4"
        if asp not in videos and candidate.exists():
            videos[asp] = candidate
    write_embed_snippet(script, out_dir, videos)
    write_metadata(script, beats, out_dir, videos)

    print("\nDone.")
    for k, v in videos.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
