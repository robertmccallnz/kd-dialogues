"""
TTS wrapper — synthesises each thinker's line as a single-voice mp3.

Backends (in preference order):

1. `asi-text-to-speech` CLI — the Perplexity sandbox path (default).
2. Anything you set via the `KD_TTS_CMD` env var. It should be a shell command
   containing `{text_file}`, `{voice}`, and `{out}` placeholders. E.g.:

       export KD_TTS_CMD='piper --model {voice}.onnx -f {text_file} -o {out}'

3. If nothing is available, we fall back to a clear error — or, if
   `KD_TTS_ALLOW_SILENCE=1`, a 4-second silent mp3 so pipelines can still be
   tested end-to-end without cloud TTS.
"""

from __future__ import annotations
import json, os, shutil, subprocess
from pathlib import Path


def _asi_available() -> bool:
    return shutil.which("asi-text-to-speech") is not None


def synth_line(text: str, voice: str, out_path: Path) -> Path:
    """Synthesise `text` in `voice`, save to `out_path` (mp3)."""
    txt_path = out_path.with_suffix(".txt")
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(text.strip() + "\n", encoding="utf-8")

    custom = os.environ.get("KD_TTS_CMD")
    if custom:
        cmd = custom.format(text_file=str(txt_path), voice=voice, out=str(out_path))
        subprocess.check_call(cmd, shell=True)
        return out_path

    if _asi_available():
        payload = {"file_path": str(txt_path), "voice": voice}
        subprocess.check_call(["asi-text-to-speech", json.dumps(payload)])
        generated = txt_path.with_suffix(".mp3")
        if generated.exists() and generated != out_path:
            generated.rename(out_path)
        return out_path

    if os.environ.get("KD_TTS_ALLOW_SILENCE") == "1":
        subprocess.check_call([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", "4", "-c:a", "libmp3lame", str(out_path),
        ])
        return out_path

    raise RuntimeError(
        "No TTS backend available.\n"
        "Options:\n"
        "  1. Run inside a Perplexity sandbox (provides `asi-text-to-speech`).\n"
        "  2. Set KD_TTS_CMD to a shell command using {text_file}, {voice}, {out}.\n"
        "  3. Set KD_TTS_ALLOW_SILENCE=1 to write silent placeholders (for dev only)."
    )


def build_audio_mix(beats: list[dict], audio_dir: Path, total: float, out: Path) -> Path:
    """
    Mix all six voice tracks into one audio_mix.m4a with the same beat timing
    the video will use. Each beat is delayed to its `start` (seconds).
    """
    inputs: list[str] = []
    filters: list[str] = []
    for i, b in enumerate(beats):
        inputs.extend(["-i", str(audio_dir / f"{b['slug']}.mp3")])
        delay = int(b["start"] * 1000)
        filters.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
    mix_inputs = "".join(f"[a{i}]" for i in range(len(beats)))
    filters.append(f"{mix_inputs}amix=inputs={len(beats)}:duration=longest:normalize=0[out]")
    fg = ";".join(filters)
    subprocess.check_call([
        "ffmpeg","-y", *inputs,
        "-filter_complex", fg,
        "-map","[out]","-t", f"{total:.2f}",
        "-c:a","aac","-b:a","192k", str(out),
    ])
    return out
