"""
kd-dialogues audio-only renderer.

Usage:
    python -m kd.audio.render episodes/001-hegemony-and-mutual-aid/script.yml
    python -m kd.audio.render episodes/... --skip-tts             # reuse audio/ cache
    python -m kd.audio.render episodes/... --transcript           # also write transcript.md
    python -m kd.audio.render episodes/... --no-waveform          # skip waveform.png
"""

from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
import yaml

from ..tts import synth_line
from ..render_common import probe_duration


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
THINKERS_ROOT = REPO_ROOT / "thinkers"

DEFAULT_NARRATOR_VOICE = "kore"
DEFAULT_TAIL_MS = 400
ACT_GAP_MS = 900
COLD_OPEN_TAIL_MS = 700


def load_thinker(slug: str) -> dict:
    voice_path = THINKERS_ROOT / slug / "voice.yml"
    if not voice_path.exists():
        raise FileNotFoundError(f"Missing thinker profile: {voice_path}")
    data = yaml.safe_load(voice_path.read_text())
    data["slug"] = slug
    return data


def resolve(script_path: Path) -> dict:
    """Load script.yml, validate cast, expand turns into an ordered timeline."""
    script = yaml.safe_load(script_path.read_text())

    cast = script.get("cast") or []
    if not (2 <= len(cast) <= 6):
        raise SystemExit(f"[audio] cast must have 2–6 thinkers, got {len(cast)}")

    # Resolve every cast member's voice profile up front
    profiles = {slug: load_thinker(slug) for slug in cast}
    narrator_voice = script.get("narrator_voice", DEFAULT_NARRATOR_VOICE)

    # Build a flat ordered list of "cues" (narrator or thinker lines).
    # Each cue: {kind, voice, say, tail_ms, label, act_title}
    cues: list[dict] = []
    counter = [0]  # mutable counter for stable file naming

    def add_cue(kind: str, voice: str, say: str, tail_ms: int, label: str, act_title: str | None):
        counter[0] += 1
        cues.append({
            "index": counter[0],
            "kind": kind,           # "narrator" | "turn"
            "voice": voice,
            "say": say.strip(),
            "tail_ms": tail_ms,
            "label": label,          # for filename + transcript
            "act_title": act_title,
        })

    if script.get("cold_open"):
        add_cue("narrator", narrator_voice, script["cold_open"], COLD_OPEN_TAIL_MS,
                "cold-open", None)

    for act in script["acts"]:
        act_title = act.get("title", "")
        if act.get("intro"):
            add_cue("narrator", narrator_voice, act["intro"], DEFAULT_TAIL_MS,
                    f"act-intro-{_slugify(act_title)}", act_title)
        for i, t in enumerate(act.get("turns", []), start=1):
            slug = t["thinker"]
            if slug not in profiles:
                raise SystemExit(f"[audio] turn references '{slug}' but it's not in the cast")
            add_cue("turn",
                    voice=profiles[slug]["tts_voice"],
                    say=t["say"],
                    tail_ms=t.get("tail_ms", DEFAULT_TAIL_MS),
                    label=f"{slug}-{i:02d}",
                    act_title=act_title)
        # Extra breath between acts
        if cues:
            cues[-1]["tail_ms"] = max(cues[-1]["tail_ms"], ACT_GAP_MS)

    if script.get("end_card"):
        add_cue("narrator", narrator_voice, script["end_card"], DEFAULT_TAIL_MS,
                "end-card", None)

    script["_cues"] = cues
    script["_profiles"] = profiles
    script["_narrator_voice"] = narrator_voice
    return script


def _slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.strip().lower()).strip("-") or "seg"


def synthesise_cues(cues: list[dict], audio_dir: Path) -> None:
    """One mp3 per cue, cached by filename."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    for c in cues:
        fname = f"{c['index']:03d}-{c['label']}.mp3"
        out = audio_dir / fname
        c["mp3"] = out
        if out.exists():
            print(f"  (cached) {fname}")
            continue
        print(f"  synth {fname}  voice={c['voice']}")
        synth_line(c["say"], c["voice"], out)


def stitch(cues: list[dict], out_mp3: Path, metadata: dict) -> float:
    """
    Concatenate every cue mp3 with a per-cue tail silence, then re-encode to
    an MP3 with ID3 tags. Returns total runtime in seconds.
    """
    concat_parts: list[str] = []
    filters: list[str] = []
    total_ms = 0
    beats: list[dict] = []
    for i, c in enumerate(cues):
        dur = probe_duration(c["mp3"])
        beats.append({
            "index": c["index"], "kind": c["kind"], "label": c["label"],
            "voice": c["voice"], "act_title": c["act_title"],
            "start_ms": total_ms,
            "duration_ms": int(dur * 1000),
        })
        concat_parts.extend(["-i", str(c["mp3"])])
        filters.append(f"[{i}:a]apad=pad_dur={c['tail_ms']}ms[a{i}]")
        total_ms += int(dur * 1000) + c["tail_ms"]

    concat_inputs = "".join(f"[a{i}]" for i in range(len(cues)))
    filters.append(f"{concat_inputs}concat=n={len(cues)}:v=0:a=1[out]")
    fg = ";".join(filters)

    # Build ID3 tag args
    tag_args: list[str] = []
    if metadata.get("title"):    tag_args += ["-metadata", f"title={metadata['title']}"]
    if metadata.get("subtitle"): tag_args += ["-metadata", f"album={metadata['subtitle']}"]
    authors = metadata.get("authors") or "The Kiwi Dialectic"
    # authors may be a string or a list — support both
    if isinstance(authors, list):
        artist = ", ".join(authors) if authors else "The Kiwi Dialectic"
    else:
        artist = str(authors)
    tag_args += ["-metadata", f"artist={artist}"]
    tag_args += ["-metadata", f"genre=Political dialogue"]
    lic = metadata.get("license", "CC BY-SA 4.0")
    comment_bits = [f"License: {lic}"]
    if metadata.get("cast"):
        comment_bits.append("Cast: " + ", ".join(metadata["cast"]))
    tag_args += ["-metadata", f"comment={' · '.join(comment_bits)}"]

    subprocess.check_call([
        "ffmpeg", "-y", *concat_parts,
        "-filter_complex", fg,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-q:a", "2", "-ar", "44100", "-ac", "1",
        *tag_args,
        str(out_mp3),
    ])
    return total_ms / 1000, beats


def write_metadata(script: dict, beats: list[dict], runtime_s: float,
                   mp3_path: Path, waveform_path: Path | None, out_dir: Path) -> Path:
    md = {
        "slug": script["slug"],
        "title": script.get("title"),
        "subtitle": script.get("subtitle"),
        "cast": script.get("cast"),
        "runtime_seconds": runtime_s,
        "mp3": str(mp3_path.relative_to(out_dir)),
        "waveform": str(waveform_path.relative_to(out_dir)) if waveform_path else None,
        "acts": [a.get("title") for a in script.get("acts", [])],
        # Chapter markers: one per cue, in seconds
        "chapters": [
            {
                "start": b["start_ms"] / 1000,
                "duration": b["duration_ms"] / 1000,
                "kind": b["kind"],
                "label": b["label"],
                "act_title": b["act_title"],
            }
            for b in beats
        ],
    }
    p = out_dir / "metadata.json"
    p.write_text(json.dumps(md, indent=2), encoding="utf-8")
    return p


def write_embed(script: dict, mp3_path: Path, waveform_path: Path | None, out_dir: Path) -> Path:
    slug = script["slug"]
    poster_attr = f'poster="{waveform_path.name}" ' if waveform_path else ""
    html = f"""<!-- kd-dialogues audio embed :: {slug} -->
<!-- Replace the src below with a public URL to the mp3, e.g. a GitHub raw URL. -->
<figure style="max-width:640px;margin:1.4rem auto;font-family:'Noto Serif',Georgia,serif;color:#1c1816">
  {f'<img src="{waveform_path.name}" alt="Waveform" style="width:100%;display:block;background:#f5ecd8;border:1px solid #1c1816">' if waveform_path else ''}
  <audio controls preload="metadata" style="width:100%;margin-top:8px">
    <source src="{{MP3_URL}}" type="audio/mpeg">
    Your browser cannot play this audio. <a href="{{MP3_URL}}">Download the mp3</a>.
  </audio>
  <figcaption style="font-style:italic;text-align:center;color:#4a4238;margin-top:6px">
    {script.get('title','')} — {script.get('subtitle','')}
  </figcaption>
</figure>
"""
    p = out_dir / "embed.html"
    p.write_text(html, encoding="utf-8")
    return p


def write_transcript(script: dict, beats: list[dict], out_dir: Path) -> Path:
    lines: list[str] = [f"# {script.get('title','')}", ""]
    if script.get("subtitle"):
        lines += [f"_{script['subtitle']}_", ""]
    if script.get("cast"):
        lines += [f"**Cast:** {', '.join(script['cast'])}  ", ""]

    # Rebuild the readable transcript from script + beats (for timing)
    beat_idx = 0
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s//60:02d}:{s%60:02d}"

    if script.get("cold_open"):
        b = beats[beat_idx]; beat_idx += 1
        lines += [f"**[{_fmt(b['start_ms'])}] Narrator**", "", script["cold_open"].strip(), ""]

    for act in script["acts"]:
        lines += [f"## {act.get('title','')}", ""]
        if act.get("intro"):
            b = beats[beat_idx]; beat_idx += 1
            lines += [f"**[{_fmt(b['start_ms'])}] Narrator**", "", act["intro"].strip(), ""]
        for t in act.get("turns", []):
            b = beats[beat_idx]; beat_idx += 1
            lines += [f"**[{_fmt(b['start_ms'])}] {t['thinker'].title()}**", "",
                      t["say"].strip(), ""]

    if script.get("end_card"):
        b = beats[beat_idx]; beat_idx += 1
        lines += [f"**[{_fmt(b['start_ms'])}] Narrator**", "", script["end_card"].strip(), ""]

    p = out_dir / "transcript.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", type=Path, help="Path to an episode script.yml")
    ap.add_argument("--skip-tts", action="store_true",
                    help="Skip TTS synthesis (reuse existing audio/*.mp3)")
    ap.add_argument("--no-waveform", action="store_true",
                    help="Skip waveform.png rendering")
    ap.add_argument("--transcript", action="store_true",
                    help="Also write transcript.md")
    args = ap.parse_args()

    script_path = args.script.resolve()
    out_dir = script_path.parent
    audio_dir = out_dir / "audio"
    print(f"[audio] loading {script_path.name}")
    script = resolve(script_path)

    print(f"[audio] {len(script['_cues'])} cues across {len(script['acts'])} act(s), cast: {script['cast']}")

    if not args.skip_tts:
        print("[audio] synthesising cues...")
        synthesise_cues(script["_cues"], audio_dir)
    else:
        # attach mp3 paths so stitch() can read them
        for c in script["_cues"]:
            c["mp3"] = audio_dir / f"{c['index']:03d}-{c['label']}.mp3"
            if not c["mp3"].exists():
                raise SystemExit(f"[audio] --skip-tts but missing {c['mp3']}")

    mp3_path = out_dir / f"{script['slug']}.mp3"
    print(f"[audio] stitching → {mp3_path.name}")
    runtime, beats = stitch(script["_cues"], mp3_path, {
        "title": script.get("title"),
        "subtitle": script.get("subtitle"),
        "authors": script.get("authors"),
        "license": script.get("license"),
        "cast": script.get("cast"),
    })
    print(f"[audio] runtime: {int(runtime // 60)}:{int(runtime % 60):02d}")

    waveform_path = None
    if not args.no_waveform:
        from .waveform import render as render_waveform
        waveform_path = out_dir / f"{script['slug']}.waveform.png"
        print(f"[audio] rendering waveform → {waveform_path.name}")
        render_waveform(mp3_path, waveform_path, title=script.get("title", ""),
                        subtitle=script.get("subtitle", ""),
                        cast=script.get("cast", []))

    write_metadata(script, beats, runtime, mp3_path, waveform_path, out_dir)
    write_embed(script, mp3_path, waveform_path, out_dir)
    if args.transcript:
        p = write_transcript(script, beats, out_dir)
        print(f"[audio] transcript → {p.name}")

    print("[audio] done.")


if __name__ == "__main__":
    main()
