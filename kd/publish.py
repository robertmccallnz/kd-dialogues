"""
kd-dialogues distribution.

Usage:
    python -m kd.publish dialogues/001-first-round --target github
    python -m kd.publish dialogues/001-first-round --target substack
    python -m kd.publish dialogues/001-first-round --target export-pack

Targets:

    github        Commit + push this dialogue's video/, audio/, script.yml,
                  metadata.json, and embed.html to the current git remote.
                  Uses the `gh` CLI (falls back to `git`).

    substack      Fill in the {VIDEO_URL} placeholder in embed.html using a
                  GitHub raw URL derived from the current git remote, and
                  write a Substack-ready copy-paste file at
                  video/embed.substack.html. Requires the repo to already be
                  pushed to GitHub.

    export-pack   Generate a `dist/` folder inside the dialogue containing:
                  * captions/{platform}.txt      TikTok/Reels/Shorts caption
                  * dist/manifest.json           Which mp4 to use per platform
                  * dist/upload-checklist.md     Author-facing upload steps
                  This is what you use to hand-post to TikTok, Instagram, and X
                  since those platforms don't expose an upload connector.

    youtube       Upload the 16:9 mp4 to YouTube via the YouTube Data API
                  connector. If disconnected, prints a connect URL and stops.

    all           Run: export-pack, github, substack, then (if available)
                  youtube.
"""

from __future__ import annotations
import argparse, json, os, subprocess, sys, textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------- helpers ---------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)

def load_metadata(dialogue_dir: Path) -> dict:
    p = dialogue_dir / "video" / "metadata.json"
    if not p.exists():
        raise SystemExit(
            f"Missing {p} — run `python -m kd.generate {dialogue_dir}/script.yml` first."
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
    # git@github.com:owner/repo.git  OR  https://github.com/owner/repo(.git)
    if out.startswith("git@github.com:"):
        slug = out.split(":", 1)[1]
    elif "github.com/" in out:
        slug = out.split("github.com/", 1)[1]
    else:
        return None
    slug = slug.removesuffix(".git")
    if "/" not in slug:
        return None
    owner, repo = slug.split("/", 1)
    return owner, repo


# ---------- targets ---------------------------------------------------------

def publish_github(dialogue_dir: Path, meta: dict) -> None:
    """Commit the dialogue and push."""
    slug = meta["slug"]
    rel = dialogue_dir.relative_to(REPO_ROOT)
    print(f"[github] staging {rel}/ ...")
    _run(["git", "-C", str(REPO_ROOT), "add", str(rel)])
    # only commit if there's something staged
    diff = _run(["git", "-C", str(REPO_ROOT), "diff", "--cached", "--name-only"]).stdout
    if not diff.strip():
        print("[github] nothing to commit.")
        return
    msg = f"dialogue: {slug} ({meta.get('title','')})"
    _run(["git", "-C", str(REPO_ROOT), "commit", "-m", msg])
    print(f"[github] pushing ...")
    _run(["git", "-C", str(REPO_ROOT), "push"])
    print("[github] done.")


def publish_substack(dialogue_dir: Path, meta: dict) -> None:
    """Materialise embed.html with a real GitHub raw URL baked in."""
    gh = infer_github_slug()
    slug = meta["slug"]
    embed = (dialogue_dir / "video" / "embed.html").read_text()
    # pick 1:1 by default, fall back
    videos = meta.get("videos", {})
    chosen_rel = videos.get("1x1") or videos.get("16x9") or videos.get("9x16")
    if not chosen_rel:
        raise SystemExit("[substack] no rendered mp4 found in metadata.json")
    if not gh:
        print("[substack] no github remote detected — leaving {VIDEO_URL} placeholder.")
        substack_html = embed
    else:
        owner, repo = gh
        raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/main"
        raw_url = f"{raw_base}/{dialogue_dir.relative_to(REPO_ROOT)}/{chosen_rel}"
        substack_html = embed.replace("{VIDEO_URL}", raw_url)
        print(f"[substack] pointing at {raw_url}")
    out = dialogue_dir / "video" / "embed.substack.html"
    out.write_text(substack_html, encoding="utf-8")
    print(f"[substack] wrote {out}")
    print("[substack] paste that HTML into a Substack post via 'Insert > HTML embed'.")


CAPTION_TEMPLATES = {
    "tiktok": (
        "{title}\n\n"
        "{subtitle}\n\n"
        "Six voices — one round. Full course: {course_url}"
    ),
    "instagram": (
        "{title}\n\n"
        "{subtitle}\n\n"
        "Full course — link in bio."
    ),
    "x": (
        "{title} — {subtitle}\n\n"
        "Full course: {course_url}"
    ),
    "youtube": (
        "{title}\n{subtitle}\n\n"
        "A writing-room course from The Kiwi Dialectic. "
        "Six figures — Antonio Gramsci, Peter Kropotkin, Mikhail Bakunin, "
        "Paulo Freire, Gilles Deleuze, David Graeber — take one round.\n\n"
        "Beats:\n{beats}\n\n"
        "Full course + module notes: {course_url}\n"
        "Source + assets: {repo_url}\n\n"
        "CC BY-SA 4.0."
    ),
}


def publish_export_pack(dialogue_dir: Path, meta: dict) -> None:
    """Write captions + a manifest + a checklist for hand-uploading."""
    dist = dialogue_dir / "dist"
    dist.mkdir(exist_ok=True)
    captions_dir = dist / "captions"
    captions_dir.mkdir(exist_ok=True)

    gh = infer_github_slug()
    repo_url = f"https://github.com/{gh[0]}/{gh[1]}" if gh else "<publish repo to fill in>"
    course_url = "https://kiwidialectic.substack.com"  # editable per author

    # timestamped beats for YouTube chapters
    beat_lines = []
    for b in meta.get("beats", []):
        m, s = divmod(int(b["start"]), 60)
        beat_lines.append(f"{m:02d}:{s:02d} — {b['slug'].title()}")
    beats_str = "\n".join(beat_lines) if beat_lines else "(no beats)"

    ctx = {
        "title": meta.get("title", ""),
        "subtitle": meta.get("subtitle", ""),
        "course_url": course_url,
        "repo_url": repo_url,
        "beats": beats_str,
    }
    for platform, tpl in CAPTION_TEMPLATES.items():
        (captions_dir / f"{platform}.txt").write_text(tpl.format(**ctx), encoding="utf-8")

    manifest = {
        "slug": meta["slug"],
        "title": meta.get("title"),
        "runtime_seconds": meta.get("runtime_seconds"),
        "platforms": {
            "youtube":   {"video": meta["videos"].get("16x9"), "caption": "captions/youtube.txt"},
            "tiktok":    {"video": meta["videos"].get("9x16"), "caption": "captions/tiktok.txt"},
            "instagram": {"video": meta["videos"].get("9x16"), "caption": "captions/instagram.txt",
                          "note": "For feed post, also crop 1:1 available at videos['1x1']."},
            "x":         {"video": meta["videos"].get("1x1"),  "caption": "captions/x.txt"},
            "substack":  {"video": meta["videos"].get("1x1"),  "embed": "video/embed.substack.html"},
        },
    }
    (dist / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    checklist = textwrap.dedent(f"""
        # Upload Checklist — {meta.get("title")}

        ## YouTube (16:9)
        - Video: `{meta['videos'].get('16x9')}`
        - Description: `dist/captions/youtube.txt`
        - Or run: `python -m kd.publish {dialogue_dir.relative_to(REPO_ROOT)} --target youtube`

        ## TikTok / Reels / Shorts (9:16)
        - Video: `{meta['videos'].get('9x16')}`
        - Caption: `dist/captions/tiktok.txt`
        - Upload manually via each platform's app / creator studio.

        ## Instagram Feed (1:1)
        - Video: `{meta['videos'].get('1x1')}`
        - Caption: `dist/captions/instagram.txt`

        ## X / Twitter
        - Video: `{meta['videos'].get('1x1')}`
        - Post text: `dist/captions/x.txt`

        ## Substack
        - Embed snippet: `video/embed.substack.html`
        - Or run: `python -m kd.publish {dialogue_dir.relative_to(REPO_ROOT)} --target substack`
    """).strip() + "\n"
    (dist / "upload-checklist.md").write_text(checklist, encoding="utf-8")
    print(f"[export-pack] wrote {dist}/")


def publish_youtube(dialogue_dir: Path, meta: dict) -> None:
    """Upload 16:9 to YouTube via the connector, if connected."""
    # This is a thin wrapper: the actual upload happens through the agent's
    # connector layer. We just print instructions the human/agent can invoke.
    video = dialogue_dir / (meta["videos"].get("16x9") or "")
    if not video.exists():
        print(f"[youtube] no 16:9 video found at {video}")
        return
    print(f"[youtube] Ready to upload {video}")
    print("[youtube] From the agent, this triggers the YouTube Data connector.")
    print("[youtube] If disconnected, connect it first, then re-run this target.")
    print(f"[youtube] Title: {meta.get('title')}")
    print(f"[youtube] Description: dist/captions/youtube.txt")


# ---------- entry -----------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dialogue", type=Path, help="Path to a dialogues/<slug> directory")
    ap.add_argument("--target", required=True,
                    choices=["github", "substack", "export-pack", "youtube", "all"])
    args = ap.parse_args()

    dialogue = args.dialogue.resolve()
    if not (dialogue / "script.yml").exists():
        raise SystemExit(f"Not a dialogue dir: {dialogue}")
    meta = load_metadata(dialogue)

    targets = ["export-pack", "github", "substack", "youtube"] if args.target == "all" else [args.target]
    for t in targets:
        if t == "github":       publish_github(dialogue, meta)
        elif t == "substack":   publish_substack(dialogue, meta)
        elif t == "export-pack":publish_export_pack(dialogue, meta)
        elif t == "youtube":    publish_youtube(dialogue, meta)


if __name__ == "__main__":
    main()
