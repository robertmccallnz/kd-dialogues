"""
kd-dialogues :: audio publishing.

Usage:
    python -m kd.publish_audio episodes/001-housing-and-hegemony --target github
    python -m kd.publish_audio episodes/001-housing-and-hegemony --target substack
    python -m kd.publish_audio episodes/001-housing-and-hegemony --target export-pack
    python -m kd.publish_audio episodes/001-housing-and-hegemony --target all

Targets:

    github        Commit + push this episode's mp3, waveform.png, script.yml,
                  metadata.json, transcript.md, and audio/ cues to the current
                  git remote.

    substack      Fill in the {MP3_URL} placeholder in embed.html using a
                  GitHub raw URL derived from the current git remote, and
                  write a Substack-ready copy-paste file at
                  embed.substack.html. Requires the repo to already be pushed.

    export-pack   Generate a `dist/` folder inside the episode containing:
                  * captions/{platform}.txt      Substack/X caption
                  * dist/manifest.json           MP3 + waveform per surface
                  * dist/upload-checklist.md     Author-facing upload steps

    all           Run: export-pack, github, substack.
"""

from __future__ import annotations
import argparse, json, subprocess, textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------- helpers ---------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def load_metadata(episode_dir: Path) -> dict:
    p = episode_dir / "metadata.json"
    if not p.exists():
        raise SystemExit(
            f"Missing {p} — run `python -m kd.audio.render {episode_dir}/script.yml` first."
        )
    return json.loads(p.read_text())


def infer_github_slug() -> tuple[str, str] | None:
    """Return (owner, repo) from the current git remote, or None."""
    try:
        out = _run(["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"]).stdout.strip()
    except Exception:
        return None
    if not out:
        return None
    if out.startswith("git@github.com:"):
        slug = out.split(":", 1)[1]
    elif "github.com/" in out:
        slug = out.split("github.com/", 1)[1]
    elif "git-agent-proxy.perplexity.ai/" in out:
        slug = out.split("git-agent-proxy.perplexity.ai/", 1)[1]
    else:
        return None
    slug = slug.removesuffix(".git")
    if "/" not in slug:
        return None
    owner, repo = slug.split("/", 1)
    return owner, repo


# ---------- targets ---------------------------------------------------------

def publish_github(episode_dir: Path, meta: dict) -> None:
    """Commit the episode and push."""
    slug = meta["slug"]
    rel = episode_dir.relative_to(REPO_ROOT)
    print(f"[github] staging {rel}/ ...")
    _run(["git", "-C", str(REPO_ROOT), "add", str(rel)])
    diff = _run(["git", "-C", str(REPO_ROOT), "diff", "--cached", "--name-only"]).stdout
    if not diff.strip():
        print("[github] nothing to commit.")
        return
    msg = f"episode: {slug} ({meta.get('title', '')})"
    _run(["git", "-C", str(REPO_ROOT), "commit", "-m", msg])
    print("[github] pushing ...")
    _run(["git", "-C", str(REPO_ROOT), "push"])
    print("[github] done.")


def publish_substack(episode_dir: Path, meta: dict) -> None:
    """Materialise embed.html with a real GitHub raw URL baked in."""
    gh = infer_github_slug()
    embed = (episode_dir / "embed.html").read_text()
    mp3_rel = meta.get("mp3")
    if not mp3_rel:
        raise SystemExit("[substack] no mp3 found in metadata.json")
    if not gh:
        print("[substack] no github remote detected — leaving {MP3_URL} placeholder.")
        substack_html = embed
    else:
        owner, repo = gh
        raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/main"
        raw_url = f"{raw_base}/{episode_dir.relative_to(REPO_ROOT)}/{mp3_rel}"
        substack_html = embed.replace("{MP3_URL}", raw_url)
        print(f"[substack] pointing at {raw_url}")
    out = episode_dir / "embed.substack.html"
    out.write_text(substack_html, encoding="utf-8")
    print(f"[substack] wrote {out}")
    print("[substack] paste that HTML into a Substack post via 'Insert > HTML embed'.")


CAPTION_TEMPLATES = {
    "substack": (
        "{title}\n\n"
        "{subtitle}\n\n"
        "Runtime: {runtime}. Featuring: {cast}.\n"
        "Full course + notes: {course_url}"
    ),
    "x": (
        "{title} — {subtitle}\n\n"
        "New audio dialogue. {cast}.\n"
        "Listen: {course_url}"
    ),
    "notes": (
        "{title}\n{subtitle}\n\n"
        "A kd-dialogues audio round from The Kiwi Dialectic.\n"
        "Cast: {cast}.\n\n"
        "Chapters:\n{chapters}\n\n"
        "Sources &amp; further reading:\n{sources}\n\n"
        "Full course + module notes: {course_url}\n"
        "Source + assets: {repo_url}\n\n"
        "CC BY-SA 4.0."
    ),
}


def _format_chapters(meta: dict) -> str:
    lines = []
    for c in meta.get("chapters", []):
        total = int(c["start"])
        m, s = divmod(total, 60)
        label = c.get("label", "").replace("-", " ")
        act = c.get("act_title") or ""
        prefix = f"{act} · " if act else ""
        lines.append(f"{m:02d}:{s:02d} — {prefix}{label}")
    return "\n".join(lines) if lines else "(no chapters)"


def _format_runtime(seconds: float) -> str:
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _format_sources(meta: dict) -> str:
    src = meta.get("sources") or []
    if not src:
        return "(none listed)"
    lines = []
    for s in src:
        if isinstance(s, str):
            lines.append(f"- {s}")
        elif isinstance(s, dict):
            title = s.get("title") or s.get("name") or s.get("url", "source")
            url = s.get("url", "")
            note = s.get("note")
            line = f"- {title}: {url}" if url else f"- {title}"
            if note:
                line += f" ({note})"
            lines.append(line)
    return "\n".join(lines)


def publish_export_pack(episode_dir: Path, meta: dict) -> None:
    """Write captions + a manifest + a checklist for hand-uploading."""
    dist = episode_dir / "dist"
    dist.mkdir(exist_ok=True)
    captions_dir = dist / "captions"
    captions_dir.mkdir(exist_ok=True)

    gh = infer_github_slug()
    repo_url = f"https://github.com/{gh[0]}/{gh[1]}" if gh else "<publish repo to fill in>"
    course_url = "https://kiwidialectic.substack.com"

    cast = ", ".join(name.title() for name in meta.get("cast", []))
    ctx = {
        "title": meta.get("title", ""),
        "subtitle": meta.get("subtitle", ""),
        "runtime": _format_runtime(meta.get("runtime_seconds", 0)),
        "cast": cast,
        "chapters": _format_chapters(meta),
        "sources": _format_sources(meta),
        "course_url": course_url,
        "repo_url": repo_url,
    }
    for platform, tpl in CAPTION_TEMPLATES.items():
        (captions_dir / f"{platform}.txt").write_text(tpl.format(**ctx), encoding="utf-8")

    manifest = {
        "slug": meta["slug"],
        "title": meta.get("title"),
        "runtime_seconds": meta.get("runtime_seconds"),
        "surfaces": {
            "substack": {"mp3": meta["mp3"], "embed": "embed.substack.html", "caption": "captions/substack.txt"},
            "x":        {"mp3": meta["mp3"], "waveform": meta.get("waveform"), "caption": "captions/x.txt"},
            "website":  {"mp3": meta["mp3"], "waveform": meta.get("waveform"), "embed": "embed.html"},
            "notes":    {"transcript": "transcript.md", "caption": "captions/notes.txt"},
        },
    }
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    checklist = textwrap.dedent(f"""
        # Upload Checklist — {meta.get("title")}

        Runtime: {ctx['runtime']}
        Cast: {ctx['cast']}

        ## Substack (recommended primary surface)
        - MP3: `{meta['mp3']}`
        - Embed snippet: `embed.substack.html`
        - Post text: `dist/captions/substack.txt`
        - Or run: `python -m kd.publish_audio {episode_dir.relative_to(REPO_ROOT)} --target substack`

        ## Website (six-thinkers hub)
        - Raw MP3 URL (after github push) is auto-filled into `embed.html`.
        - Waveform image: `{meta.get('waveform')}`

        ## X / Twitter
        - Media: attach `{meta.get('waveform')}` as image, link to Substack post
        - Post text: `dist/captions/x.txt`

        ## Show notes / description
        - Content: `dist/captions/notes.txt` (includes chapter markers)
        - Transcript: `transcript.md`
    """).strip() + "\n"
    (dist / "upload-checklist.md").write_text(checklist, encoding="utf-8")
    print(f"[export-pack] wrote {dist}/")


# ---------- entry -----------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episode", type=Path, help="Path to an episodes/<slug> directory")
    ap.add_argument("--target", required=True,
                    choices=["github", "substack", "export-pack", "all"])
    args = ap.parse_args()

    episode = args.episode.resolve()
    if not (episode / "script.yml").exists():
        raise SystemExit(f"Not an episode dir: {episode}")
    meta = load_metadata(episode)

    targets = ["export-pack", "github", "substack"] if args.target == "all" else [args.target]
    for t in targets:
        if t == "github":         publish_github(episode, meta)
        elif t == "substack":     publish_substack(episode, meta)
        elif t == "export-pack":  publish_export_pack(episode, meta)


if __name__ == "__main__":
    main()
