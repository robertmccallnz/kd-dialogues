"""
Build the static GitHub Pages catalogue at docs/index.html.

Reads two sources:
  * dialogues/*/video/metadata.json  — video dialogues
  * episodes/*/metadata.json         — audio episodes

Renders a cream-paper index page with an Audio Episodes section and a Video
Dialogues section. Zero build-time dependencies beyond stdlib.
"""

from __future__ import annotations
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIALOGUES = REPO / "dialogues"
EPISODES = REPO / "episodes"
OUT = REPO / "docs" / "index.html"


def collect_videos() -> list[dict]:
    entries = []
    if not DIALOGUES.exists():
        return entries
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


def collect_audio() -> list[dict]:
    entries = []
    if not EPISODES.exists():
        return entries
    for d in sorted(EPISODES.iterdir()):
        if not d.is_dir():
            continue
        meta = d / "metadata.json"
        if not meta.exists():
            continue
        m = json.loads(meta.read_text())
        m["dir"] = d.name
        entries.append(m)
    return entries


VIDEO_CARD = """\
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

AUDIO_CARD = """\
<article class="card">
  <h2>{title}</h2>
  <p class="subtitle">{subtitle}</p>
  <p class="thinkers">{cast}</p>
  <p class="runtime">{runtime} · {chapters} chapters</p>
  <audio controls preload="metadata" style="width:100%;margin:0.4rem 0">
    <source src="../episodes/{dirname}/{mp3}" type="audio/mpeg">
    Your browser cannot play this audio.
    <a href="../episodes/{dirname}/{mp3}">Download the mp3</a>.
  </audio>
  <div class="videos">
    <a class="video-link" href="../episodes/{dirname}/{mp3}">MP3</a>
    <a class="video-link" href="../episodes/{dirname}/transcript.md">Transcript</a>
    {waveform_link}
  </div>
  {sources_block}
  <p class="path">episodes/{dirname}/</p>
</article>
"""

AUDIO_WAVEFORM_LINK = '<a class="video-link" href="../episodes/{dirname}/{waveform}">Waveform</a>'


def _format_runtime(seconds: float) -> str:
    total = int(round(float(seconds or 0)))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _render_sources(sources: list) -> str:
    if not sources:
        return ""
    items = []
    for s in sources:
        if isinstance(s, str):
            items.append(f"<li>{s}</li>")
        elif isinstance(s, dict):
            title = s.get("title") or s.get("name") or s.get("url", "source")
            url = s.get("url", "")
            note = s.get("note", "")
            body = f'<a href="{url}">{title}</a>' if url else title
            if note:
                body += f' <span class="src-note">— {note}</span>'
            items.append(f"<li>{body}</li>")
    return (
        '<details class="sources"><summary>Sources &amp; further reading</summary>'
        f'<ul>{"".join(items)}</ul></details>'
    )


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
    h2.section {{
      font-size: 1rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin: 2.4rem 0 0.6rem;
      color: var(--brick);
      border-bottom: 1px solid var(--ochre);
      padding-bottom: 0.3rem;
    }}
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
    details.sources {{ margin: 0.6rem 0 0.2rem; font-size: 0.9rem; }}
    details.sources summary {{ cursor: pointer; color: var(--brick); }}
    details.sources ul {{ margin: 0.4rem 0 0 1.2rem; padding: 0; }}
    details.sources a {{ color: var(--ink); }}
    .src-note {{ color: #4a4238; font-style: italic; }}
    footer {{ margin-top: 3rem; font-size: 0.85rem; color: #7a6f5c; }}
    footer a {{ color: var(--brick); }}
  </style>
</head>
<body>
  <header>
    <h1>kd-dialogues</h1>
    <p class="lede">A writing-room engine for political dialogues. Audio episodes, video dialogues, and the thinker roster that voices them.</p>
  </header>

  <main>
    <h2 class="section">Audio Episodes</h2>
{audio_cards}

    <h2 class="section">Video Dialogues</h2>
{video_cards}
  </main>

  <footer>
    <p>Source: <a href="https://github.com/robertmccallnz/kd-dialogues">github.com/robertmccallnz/kd-dialogues</a> · Made for <a href="https://kiwidialectic.substack.com">The Kiwi Dialectic</a>.</p>
    <p>Voices synthesised from documented cadence, vernacular, and delivery. Portraits and text CC BY-SA 4.0.</p>
  </footer>
</body>
</html>
"""


def render() -> None:
    video_entries = collect_videos()
    audio_entries = collect_audio()

    audio_cards = []
    for e in audio_entries:
        wf = e.get("waveform")
        wf_link = AUDIO_WAVEFORM_LINK.format(dirname=e["dir"], waveform=wf) if wf else ""
        audio_cards.append(AUDIO_CARD.format(
            title=e.get("title", e.get("slug", "")),
            subtitle=e.get("subtitle", ""),
            cast=" · ".join(c.title() for c in e.get("cast", [])),
            runtime=_format_runtime(e.get("runtime_seconds", 0)),
            chapters=len(e.get("chapters", [])),
            dirname=e["dir"],
            mp3=e.get("mp3", ""),
            waveform_link=wf_link,
            sources_block=_render_sources(e.get("sources", [])),
        ))
    audio_body = "\n".join(audio_cards) if audio_cards \
        else "<p><em>No audio episodes yet. Add one under <code>episodes/</code>.</em></p>"

    video_cards = []
    for e in video_entries:
        video_links = "\n    ".join(
            VIDEO_LINK.format(dirname=e["dir"], path=path, label=asp)
            for asp, path in e.get("videos", {}).items()
        ) or "<em>No videos rendered yet.</em>"
        video_cards.append(VIDEO_CARD.format(
            title=e.get("title", e["slug"]),
            subtitle=e.get("subtitle", ""),
            thinkers=" · ".join(t.title() for t in e.get("thinkers", [])),
            runtime=int(e.get("runtime_seconds", 0)),
            beats=len(e.get("beats", [])),
            video_links=video_links,
            dirname=e["dir"],
        ))
    video_body = "\n".join(video_cards) if video_cards \
        else "<p><em>No video dialogues yet. Add one under <code>dialogues/</code>.</em></p>"

    OUT.write_text(
        PAGE.format(audio_cards=audio_body, video_cards=video_body),
        encoding="utf-8",
    )
    print(f"wrote {OUT} · {len(audio_entries)} audio · {len(video_entries)} video")


if __name__ == "__main__":
    render()
