"""
kd-dialogues audio drafter.

Generate a skeleton episode script.yml from a topic + cast + optional act titles.
The skeleton is filled with prompts and voice-profile hints so you know exactly
what to write in each turn slot. You always edit the file before rendering.

Usage:
    python -m kd.audio.draft \\
        --slug hegemony-and-mutual-aid \\
        --title "How do you break a hegemony that feels like weather?" \\
        --cast gramsci kropotkin \\
        --acts "I. Diagnosis" "II. Disagreement" "III. Proposal" \\
        --turns-per-act 4

Result:
    episodes/<slug>/script.yml    (ready to edit; NEVER rendered until you edit)
"""

from __future__ import annotations
import argparse
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parent.parent.parent
THINKERS = REPO / "thinkers"
EPISODES = REPO / "episodes"


def _voice_hints(slug: str) -> tuple[str, list[str], list[str]]:
    voice_path = THINKERS / slug / "voice.yml"
    if not voice_path.exists():
        raise SystemExit(f"[draft] no thinker profile at {voice_path}")
    v = yaml.safe_load(voice_path.read_text())
    display = v.get("full_name") or v.get("display_name") or slug.title()
    vernacular = v.get("vernacular", [])[:3]
    tags = v.get("delivery_tags", [])[:4]
    return display, vernacular, tags


def _prompt_block(slug: str, act_title: str) -> str:
    display, vernacular, tags = _voice_hints(slug)
    lines = [f"[write {display}'s response here — {act_title}]"]
    if vernacular:
        lines.append("")
        lines.append(f"# Voice hints for {display}:")
        for v in vernacular:
            lines.append(f"#   - {v}")
    if tags:
        lines.append(f"# Delivery tags available: {', '.join(tags)}")
    return "\n".join(lines)


def _numeric_prefix(n: int, existing: list[Path]) -> str:
    """Pick a monotonically-increasing 3-digit prefix for the new episode dir."""
    used = set()
    for p in existing:
        stem = p.name.split("-", 1)[0]
        if stem.isdigit():
            used.add(int(stem))
    idx = max(used, default=0) + 1
    return f"{idx:03d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True, help="Episode slug (e.g. hegemony-and-mutual-aid)")
    ap.add_argument("--title", required=True, help="Episode title")
    ap.add_argument("--subtitle", default="", help="Optional subtitle")
    ap.add_argument("--cast", nargs="+", required=True,
                    help="2–6 thinker slugs (must exist in thinkers/)")
    ap.add_argument("--acts", nargs="+", default=["I. Diagnosis", "II. Disagreement", "III. Proposal"],
                    help="Act titles (default: three-act structure)")
    ap.add_argument("--turns-per-act", type=int, default=4,
                    help="Turns per act. Rotates through the cast.")
    ap.add_argument("--narrator-voice", default="kore")
    ap.add_argument("--force", action="store_true", help="Overwrite if the episode dir exists")
    args = ap.parse_args()

    if not (2 <= len(args.cast) <= 6):
        raise SystemExit(f"[draft] cast must have 2–6 thinkers, got {len(args.cast)}")

    # Sanity-check the cast up front so the drafter fails fast on typos
    for slug in args.cast:
        _voice_hints(slug)  # will raise if missing

    EPISODES.mkdir(exist_ok=True)
    existing = sorted(p for p in EPISODES.iterdir() if p.is_dir())
    prefix = _numeric_prefix(len(existing) + 1, existing)
    ep_dir = EPISODES / f"{prefix}-{args.slug}"
    if ep_dir.exists() and not args.force:
        raise SystemExit(f"[draft] {ep_dir} already exists (pass --force to overwrite)")
    ep_dir.mkdir(exist_ok=True)

    # Build the YAML by hand so we can inject prompt comments per turn.
    yml: list[str] = [
        "# kd-dialogues audio episode — DRAFT",
        "# Fill in every '[write …]' block, then:",
        f"#   python -m kd.audio.render episodes/{ep_dir.name}/script.yml --transcript",
        "",
        f"slug: {args.slug}",
        f'title: "{args.title}"',
    ]
    if args.subtitle:
        yml.append(f'subtitle: "{args.subtitle}"')
    yml.extend([
        'authors: ["The Kiwi Dialectic"]',
        'license: "CC BY-SA 4.0"',
        "",
        f"cast: [{', '.join(args.cast)}]",
        f'narrator_voice: {args.narrator_voice}',
        "",
        f'cold_open: |',
        f'  [warm, unhurried] Round one. The problem: [write the problem in one sentence].',
        f'  {len(args.cast)} voices — { ", ".join(_voice_hints(s)[0] for s in args.cast) } — take it from here.',
        "",
        f'end_card: |',
        f'  [quiet] For The Kiwi Dialectic. Notes at kiwidialectic.substack.com.',
        "",
        "acts:",
    ])
    for act_title in args.acts:
        yml.append(f'  - title: "{act_title}"')
        yml.append(f'    intro: |')
        yml.append(f'      [neutral] {act_title}. [write one sentence framing this act].')
        yml.append(f'    turns:')
        for i in range(args.turns_per_act):
            slug = args.cast[i % len(args.cast)]
            display, vernacular, tags = _voice_hints(slug)
            yml.append(f'      - thinker: {slug}')
            yml.append(f'        # {display} — hints:')
            for v in vernacular:
                yml.append(f'        #   · {v}')
            if tags:
                yml.append(f'        # Delivery tags available: {", ".join(tags)}')
            yml.append(f'        say: |')
            yml.append(f'          [write {display}\'s response — {act_title}, turn {i+1}]')

    script_path = ep_dir / "script.yml"
    script_path.write_text("\n".join(yml) + "\n", encoding="utf-8")

    print(f"[draft] wrote {script_path}")
    print(f"[draft] {len(args.acts)} act(s) × {args.turns_per_act} turn(s) = "
          f"{len(args.acts) * args.turns_per_act} lines to write")
    print(f"[draft] cast: {', '.join(args.cast)}")
    print(f"[draft] next: edit that file, then:")
    print(f"           python -m kd.audio.render {script_path.relative_to(REPO)} --transcript")


if __name__ == "__main__":
    main()
