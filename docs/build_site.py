"""
Build the static GitHub Pages catalogue at docs/index.html.

Reads dialogues/*/video/metadata.json and renders a cream-paper index page
listing every dialogue in the repo. Zero build-time dependencies beyond stdlib
and Jinja-free string formatting — this is on purpose so `python docs/build_site.py`
works out of the box.
"""

from __future__ import annotations
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIALOGUES = REPO / "dialogues"
OUT = REPO / "docs" / "index.html"


def collect() -> list[dict]:
    entries = []
    for d in sorted(DIALOGUES.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "video" / "metadata.json"
        if not meta.exists():
            continue
        m = json.loads(meta.read_text())
        m["dir"] = d.name
        entries.append(m)
    return entries


CARD_TPL = """\
<article class="card">
  <h2>{title}</h2>
  <p class="subtitle">{subtitle}</p>
  <p class="thinkers">{thinkers}</p>
  <p class="runtime">{runtime}s · {beats} beats</p>
  <div class="videos">
    {video_links}
  </div>
  <p class="path">dialogues/{dirname}/</p>
</article>
"""

VIDEO_LINK = '<a class="video-link" href="../dialogues/{dirname}/{path}">{label}</a>'


PAGE = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>kd-dialogues — catalogue</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    :root {{
      --paper: #f5ecd8;
      --ink:   #1c1816;
      --ochre: #b0762c;
      --brick: #963c28;
    }}
    html,body {{ background: var(--paper); color: var(--ink); margin: 0; }}
    body {{
      font-family: "Noto Serif", Georgia, serif;
      max-width: 780px;
      margin: 0 auto;
      padding: 3rem 1.5rem 5rem;
      line-height: 1.55;
    }}
    header h1 {{
      font-size: 2.4rem;
      margin: 0 0 0.4rem;
      letter-spacing: 0.02em;
    }}
    header p.lede {{ margin: 0 0 2.5rem; font-style: italic; color: #4a4238; }}
    .card {{
      border-top: 2px solid var(--ochre);
      padding: 1.4rem 0 1.6rem;
    }}
    .card h2 {{ margin: 0 0 0.2rem; font-size: 1.35rem; }}
    .card .subtitle {{ margin: 0 0 0.6rem; font-style: italic; color: #4a4238; }}
    .card .thinkers {{ margin: 0 0 0.2rem; font-size: 0.95rem; color: var(--brick); }}
    .card .runtime  {{ margin: 0 0 0.6rem; font-size: 0.85rem; color: #7a6f5c; }}
    .videos {{ display: flex; gap: 0.6rem; flex-wrap: wrap; margin: 0 0 0.4rem; }}
    .video-link {{
      display: inline-block;
      padding: 0.25rem 0.7rem;
      background: var(--paper);
      color: var(--ink);
      text-decoration: none;
      border: 1px solid var(--ink);
      font-size: 0.85rem;
    }}
    .video-link:hover {{ background: var(--ink); color: var(--paper); }}
    .card .path {{
      margin: 0.4rem 0 0;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      font-size: 0.78rem;
      color: #7a6f5c;
    }}
    footer {{ margin-top: 3rem; font-size: 0.85rem; color: #7a6f5c; }}
    footer a {{ color: var(--brick); }}
  </style>
</head>
<body>
  <header>
    <h1>kd-dialogues</h1>
    <p class="lede">A writing-room engine for political dialogues. Six thinkers to start. Extensible from there.</p>
  </header>

  <main>
{cards}
  </main>

  <footer>
    <p>Source: <a href="https://github.com/robertmccallnz/kd-dialogues">github.com/robertmccallnz/kd-dialogues</a> · Made for <a href="https://kiwidialectic.substack.com">The Kiwi Dialectic</a>.</p>
    <p>Voices synthesised from documented cadence, vernacular, and delivery. Portraits and text CC BY-SA 4.0.</p>
  </footer>
</body>
</html>
"""


def render() -> None:
    entries = collect()
    cards = []
    for e in entries:
        video_links = "\n    ".join(
            VIDEO_LINK.format(dirname=e["dir"], path=path, label=asp)
            for asp, path in e.get("videos", {}).items()
        ) or "<em>No videos rendered yet.</em>"
        cards.append(CARD_TPL.format(
            title=e.get("title", e["slug"]),
            subtitle=e.get("subtitle", ""),
            thinkers=" · ".join(t.title() for t in e.get("thinkers", [])),
            runtime=int(e.get("runtime_seconds", 0)),
            beats=len(e.get("beats", [])),
            video_links=video_links,
            dirname=e["dir"],
        ))
    body = "\n".join(cards) if cards else "<p><em>No dialogues yet. Add one under <code>dialogues/</code>.</em></p>"
    OUT.write_text(PAGE.format(cards=body), encoding="utf-8")
    print(f"wrote {OUT} with {len(entries)} dialogue(s)")


if __name__ == "__main__":
    render()
