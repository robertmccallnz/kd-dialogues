"""
kd-dialogues audio-only renderer.

Usage:
    python -m kd.audio.render episodes/001-hegemony-and-mutual-aid/script.yml
    python -m kd.audio.render episodes/... --skip-tts             # reuse audio/ cache
    python -m kd.audio.render episodes/... --transcript           # also write transcript.md
    python -m kd.audio.render episodes/... --no-waveform          # skip waveform.png

The renderer groups all `turn` cues inside a single act into ONE Gemini
multi-speaker synthesis call. That locks the two thinker voices for the whole
act — no per-line drift in accent/intonation. Narrator cues (cold_open, act
intros, end_card) stay as single-voice `.txt` calls.

Gemini TTS supports max 2 unique voices per dialogue, which matches our
one-on-one dialogue pattern.
"""

from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
import yaml

from ..tts import synth_line, synth_dialogue
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


def _slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.strip().lower()).strip("-") or "seg"


def resolve(script_path: Path) -> dict:
    """Load script.yml, validate cast, expand into an ordered list of cues.

    Cue kinds:
      - "narrator": single-voice .txt render (cold_open, act intro, end_card)
      - "dialogue": multi-voice .json render (all consecutive turns in one act)
    """
    script = yaml.safe_load(script_path.read_text())

    cast = script.get("cast") or []
    if not (2 <= len(cast) <= 6):
        raise SystemExit(f"[audio] cast must have 2–6 thinkers, got {len(cast)}")

    profiles = {slug: load_thinker(slug) for slug in cast}
    narrator_voice = script.get("narrator_voice", DEFAULT_NARRATOR_VOICE)

    cues: list[dict] = []
    counter = [0]

    def add_narrator(say: str, tail_ms: int, label: str, act_title: str | None):
        counter[0] += 1
        cues.append({
            "index": counter[0],
            "kind": "narrator",
            "voice": narrator_voice,
            "say": say.strip(),
            "tail_ms": tail_ms,
            "label": label,
            "act_title": act_title,
            "turns": None,
        })

    def add_dialogue(turns: list[dict], tail_ms: int, act_title: str):
        counter[0] += 1
        # Enforce 2-voice cap here for a clearer error.
        voices = {t["voice"] for t in turns}
        if len(voices) > 2:
            raise SystemExit(
                f"[audio] act '{act_title}' uses {len(voices)} voices ({sorted(voices)}); "
                f"Gemini multi-speaker mode supports max 2. Split the act."
            )
        cues.append({
            "index": counter[0],
            "kind": "dialogue",
            "voice": ",".join(sorted(voices)),  # for logging only
            "say": None,
            "tail_ms": tail_ms,
            "label": f"act-{_slugify(act_title)}",
            "act_title": act_title,
            "turns": turns,   # list of {"voice","thinker","text","tail_ms"}
        })

    if script.get("cold_open"):
        add_narrator(script["cold_open"], COLD_OPEN_TAIL_MS, "cold-open", None)

    for act in script["acts"]:
        act_title = act.get("title", "")
        if act.get("intro"):
            add_narrator(act["intro"], DEFAULT_TAIL_MS,
                         f"act-intro-{_slugify(act_title)}", act_title)

        # Collect this act's turns into a single dialogue cue.
        raw_turns = act.get("turns", [])
        if raw_turns:
            turns = []
            for t in raw_turns:
                slug = t["thinker"]
                if slug not in profiles:
                    raise SystemExit(
                        f"[audio] turn references '{slug}' but it's not in the cast"
                    )
                turns.append({
                    "voice": profiles[slug]["tts_voice"],
                    "thinker": slug,
                    "text": t["say"].strip(),
                    "tail_ms": t.get("tail_ms", DEFAULT_TAIL_MS),
                })
            add_dialogue(turns, tail_ms=ACT_GAP_MS, act_title=act_title)

    if script.get("end_card"):
        add_narrator(script["end_card"], DEFAULT_TAIL_MS, "end-card", None)

    script["_cues"] = cues
    script["_profiles"] = profiles
    script["_narrator_voice"] = narrator_voice
    return script


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
        if c["kind"] == "narrator":
            print(f"  synth {fname}  narrator={c['voice']}")
            synth_line(c["say"], c["voice"], out)
        else:  # dialogue
            print(f"  synth {fname}  dialogue voices={c['voice']} ({len(c['turns'])} turns)")
            dialogue_input = [
                {"speaker": t["voice"], "text": t["text"]}
                for t in c["turns"]
            ]
            synth_dialogue(dialogue_input, out)


def stitch(cues: list[dict], out_mp3: Path, metadata: dict) -> tuple[float, list[dict]]:
    """Concatenate cue mp3s with tail silences, encode to ID3-tagged MP3.

    Also returns per-cue "beats" for chapter markers. For dialogue cues, the
    beat spans the whole act (since multi-speaker mode gives us one file);
    the transcript still shows every line, but chapters are act-level.
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

    tag_args: list[str] = []
    if metadata.get("title"):    tag_args += ["-metadata", f"title={metadata['title']}"]
    if metadata.get("subtitle"): tag_args += ["-metadata", f"album={metadata['subtitle']}"]
    authors = metadata.get("authors") or "The Kiwi Dialectic"
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


def _sources_lines(script: dict) -> list[str]:
    src = script.get("sources") or []
    if not src:
        return []
    out = ["", "## Sources & further reading", ""]
    for s in src:
        if isinstance(s, str):
            out.append(f"- {s}")
        elif isinstance(s, dict):
            title = s.get("title") or s.get("name") or s.get("url", "source")
            url = s.get("url", "")
            note = s.get("note")
            if url:
                line = f"- [{title}]({url})"
            else:
                line = f"- {title}"
            if note:
                line += f" — {note}"
            out.append(line)
    return out


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
        "sources": script.get("sources", []),
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
    sources_html = ""
    src = script.get("sources") or []
    if src:
        items = []
        for s in src:
            if isinstance(s, str):
                items.append(f"<li>{s}</li>")
            elif isinstance(s, dict):
                title = s.get("title") or s.get("name") or s.get("url", "source")
                url = s.get("url", "")
                note = s.get("note", "")
                if url:
                    body = f'<a href="{url}">{title}</a>'
                else:
                    body = title
                if note:
                    body += f' — <span style="color:#4a4238">{note}</span>'
                items.append(f"<li>{body}</li>")
        sources_html = (
            '<details style="margin-top:10px;font-size:0.9rem">'
            '<summary style="cursor:pointer;color:#963c28">Sources &amp; further reading</summary>'
            f'<ul style="margin:6px 0 0 1.2rem;padding:0">{"".join(items)}</ul>'
            '</details>'
        )

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
  {sources_html}
</figure>
"""
    p = out_dir / "embed.html"
    p.write_text(html, encoding="utf-8")
    return p


def write_transcript(script: dict, beats: list[dict], out_dir: Path) -> Path:
    """Rebuild readable transcript. Because dialogue cues render as a single
    mp3, act-level turns share the act cue's start time; per-line timestamps
    would be a lie without forced alignment, so we mark only the act boundary.
    """
    lines: list[str] = [f"# {script.get('title','')}", ""]
    if script.get("subtitle"):
        lines += [f"_{script['subtitle']}_", ""]
    if script.get("cast"):
        lines += [f"**Cast:** {', '.join(script['cast'])}  ", ""]

    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s//60:02d}:{s%60:02d}"

    beat_idx = 0

    if script.get("cold_open"):
        b = beats[beat_idx]; beat_idx += 1
        lines += [f"**[{_fmt(b['start_ms'])}] Narrator**", "", script["cold_open"].strip(), ""]

    for act in script["acts"]:
        lines += [f"## {act.get('title','')}", ""]
        if act.get("intro"):
            b = beats[beat_idx]; beat_idx += 1
            lines += [f"**[{_fmt(b['start_ms'])}] Narrator**", "", act["intro"].strip(), ""]
        # Dialogue cue for the whole act
        if act.get("turns"):
            b = beats[beat_idx]; beat_idx += 1
            act_start = _fmt(b["start_ms"])
            lines += [f"_Dialogue begins [{act_start}]_", ""]
            for t in act.get("turns", []):
                lines += [f"**{t['thinker'].title()}**", "", t["say"].strip(), ""]

    if script.get("end_card"):
        b = beats[beat_idx]; beat_idx += 1
        lines += [f"**[{_fmt(b['start_ms'])}] Narrator**", "", script["end_card"].strip(), ""]

    lines += _sources_lines(script)

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
