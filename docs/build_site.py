"""
Build the static GitHub Pages catalogue at docs/index.html.

Reads:
  * episodes/*/metadata.json       — audio episodes (canonical home)
  * dialogues/*/video/metadata.json — video dialogues (optional)
  * thinkers/<slug>/voice.yml       — for portrait cards
  * thinkers/<slug>/portrait.png    — copied into docs/portraits/

Renders a dark-wireframe page matching six-thinkers so both sites feel like siblings:
  --bg #0a0a0a · --fg #f4ecd8 · --kōura #e8a83a · --red #d7261e
  Bebas Neue (headings) · Inter (body)

Zero build-time dependencies beyond stdlib + a tiny hand-rolled voice.yml parser
(so this stays lock-in-free on GitHub Actions).
"""

from __future__ import annotations
import json
import shutil
from html import escape
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIALOGUES = REPO / "dialogues"
EPISODES = REPO / "episodes"
THINKERS = REPO / "thinkers"
DOCS = REPO / "docs"
OUT = DOCS / "index.html"
PORTRAITS_OUT = DOCS / "portraits"
WAVEFORMS_OUT = DOCS / "waveforms"

# Pages serves only from /docs, so audio (large mp3s) is linked out to raw
# GitHub content. Waveforms are small (~36K each) so they're copied into
# /docs/waveforms/ and served from the Pages CDN.
RAW = "https://raw.githubusercontent.com/robertmccallnz/kd-dialogues/main"

SUBSTACK = "https://kiwidialectic.substack.com"
KOFI = "https://ko-fi.com/thekiwidialectic"
REPO_URL = "https://github.com/robertmccallnz/kd-dialogues"
SIX_THINKERS_URL = "https://robertmccallnz.github.io/six-thinkers/"
CALENDAR = "https://robertmccallnz.github.io/kiwidialecticcalendar-/github-calendar-connector.html"


# ---------------- voice.yml (minimal parser, top-level scalars only) ----------------

def load_voice(slug: str) -> dict:
    """Read a couple top-level keys from thinkers/<slug>/voice.yml — no deps."""
    path = THINKERS / slug / "voice.yml"
    out = {"slug": slug}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        # only capture top-level "key: value" — indented lines are lists / children
        if line[:1] in (" ", "\t"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        # strip an inline "# comment"
        if " #" in val:
            val = val.split(" #", 1)[0].rstrip()
        # strip surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        out[key.strip()] = val
    return out


def portrait_path(slug: str) -> Path | None:
    p = THINKERS / slug / "portrait.png"
    return p if p.exists() else None


def copy_waveform(episode_dir: str, waveform_filename: str) -> str | None:
    """Copy episodes/<dir>/<waveform>.png into docs/waveforms/<dir>.png. Return
    the docs-relative path (or None if the source file is missing)."""
    src = EPISODES / episode_dir / waveform_filename
    if not src.exists():
        return None
    WAVEFORMS_OUT.mkdir(parents=True, exist_ok=True)
    dest = WAVEFORMS_OUT / f"{episode_dir}.png"
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copyfile(src, dest)
    return f"waveforms/{episode_dir}.png"


# ---------------- collectors ----------------

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


# ---------------- helpers ----------------

def fmt_runtime(seconds) -> str:
    total = int(round(float(seconds or 0)))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def render_sources(sources) -> str:
    if not sources:
        return ""
    items = []
    for s in sources:
        if isinstance(s, str):
            items.append(f"<li>{escape(s)}</li>")
        elif isinstance(s, dict):
            title = s.get("title") or s.get("name") or s.get("url", "source")
            url = s.get("url", "")
            note = s.get("note", "")
            body = f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(title)}</a>' if url else escape(title)
            if note:
                body += f' <span class="src-note">— {escape(note)}</span>'
            items.append(f"<li>{body}</li>")
    return (
        '<details class="sources"><summary>Sources &amp; further reading</summary>'
        f'<ul>{"".join(items)}</ul></details>'
    )


def portrait_card(slug: str) -> str:
    v = load_voice(slug)
    img = portrait_path(slug)
    if img:
        # ensure copied into docs/portraits/
        PORTRAITS_OUT.mkdir(parents=True, exist_ok=True)
        dest = PORTRAITS_OUT / f"{slug}.png"
        if not dest.exists() or dest.stat().st_size != img.stat().st_size:
            shutil.copyfile(img, dest)
        img_html = f'<img src="portraits/{slug}.png" alt="{escape(v.get("display_name", slug).title())} portrait" loading="lazy">'
    else:
        img_html = '<div class="portrait-placeholder">no<br>portrait<br>yet</div>'

    name = v.get("display_name") or slug.upper()
    dates = v.get("dates", "")
    tradition = v.get("tradition", "")
    return f"""      <div class="thinker-card">
        {img_html}
        <div class="thinker-meta">
          <p class="thinker-name">{escape(name)}</p>
          {f'<p class="thinker-dates">{escape(dates)}</p>' if dates else ''}
          {f'<p class="thinker-tradition">{escape(tradition)}</p>' if tradition else ''}
        </div>
      </div>"""


# ---------------- templates ----------------

CSS = r"""
:root {
  --bg: #0a0a0a;
  --bg-2: #121212;
  --bg-3: #1a1a1a;
  --fg: #f4ecd8;
  --muted: #9c8c5c;
  --line: #2a2418;
  --kōura: #e8a83a;
  --red: #d7261e;
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg); }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 17px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--kōura); text-decoration: none; }
a:hover { text-decoration: underline; }
img { max-width: 100%; height: auto; display: block; }

.shell { max-width: 1120px; margin: 0 auto; padding: 0 24px; }

/* Nav */
.site-nav {
  position: sticky; top: 0; z-index: 20;
  background: rgba(10,10,10,.85);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
  padding: 14px 0;
}
.site-nav .row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.site-nav .brand {
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .18em;
  font-size: 20px;
  color: var(--fg);
}
.site-nav .brand span { color: var(--kōura); }
.site-nav .links a {
  color: var(--fg);
  font-size: 14px;
  margin-left: 18px;
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .12em;
}
.site-nav .links a:hover { color: var(--kōura); text-decoration: none; }

/* Hero */
.hero { padding: 70px 0 50px; border-bottom: 1px solid var(--line); }
.hero .eyebrow {
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .22em;
  color: var(--kōura);
  font-size: 13px;
  margin: 0 0 14px;
  text-transform: uppercase;
}
.hero h1 {
  font-family: 'Bebas Neue', sans-serif;
  font-size: clamp(48px, 8vw, 84px);
  letter-spacing: .02em;
  line-height: .95;
  margin: 0 0 20px;
}
.hero .kaupapa { max-width: 640px; opacity: .85; font-size: 18px; margin: 0 0 22px; }
.hero .ctas a { margin-right: 10px; margin-top: 8px; }

.btn {
  display: inline-block;
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .12em;
  font-size: 14px;
  padding: 10px 18px;
  border: 1px solid var(--fg);
  color: var(--fg);
  text-decoration: none;
}
.btn:hover { background: var(--fg); color: var(--bg); text-decoration: none; }
.btn.kofi { border-color: var(--kōura); color: var(--kōura); }
.btn.kofi:hover { background: var(--kōura); color: var(--bg); }
.btn.red { border-color: var(--red); color: var(--red); }
.btn.red:hover { background: var(--red); color: var(--fg); }

/* Sections */
section.block { padding: 56px 0; border-bottom: 1px solid var(--line); }
section.block h2 {
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .02em;
  font-size: 34px;
  line-height: 1.05;
  margin: 0 0 22px;
}
.section-eyebrow {
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .22em;
  color: var(--kōura);
  font-size: 12px;
  margin: 0 0 8px;
  text-transform: uppercase;
}

/* Episode card */
.episode {
  background: var(--bg-2);
  border: 1px solid var(--line);
  padding: 26px;
  margin: 0 0 22px;
}
.episode .meta-row {
  display: flex; gap: 14px; flex-wrap: wrap; align-items: baseline;
  color: var(--muted);
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  font-size: 12px;
  letter-spacing: .1em;
  margin: 0 0 8px;
}
.episode .meta-row .runtime { margin-left: auto; }
.episode h3 {
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .02em;
  font-size: 26px;
  line-height: 1.1;
  margin: 0 0 4px;
}
.episode .subtitle { opacity: .8; font-size: 16px; margin: 0 0 18px; font-style: italic; }

.thinker-strip {
  display: grid;
  /* Force 2 columns on mobile so cast members sit side by side, even at 320px.
     Above ~640px, auto-fit fills with 140px+ columns. */
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin: 0 0 20px;
}
@media (min-width: 640px) {
  .thinker-strip {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 14px;
  }
}
.thinker-card {
  display: flex; flex-direction: column;
  background: var(--bg-3);
  border: 1px solid var(--line);
  padding: 10px;
}
.thinker-card img,
.thinker-card .portrait-placeholder {
  width: 100%;
  aspect-ratio: 3 / 4;
  object-fit: cover;
  background: var(--bg);
  border: 1px solid var(--line);
}
.thinker-card .portrait-placeholder {
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); font-size: 11px; text-align: center;
  letter-spacing: .1em; font-family: 'Bebas Neue', sans-serif;
}
.thinker-meta { padding: 10px 4px 4px; }
.thinker-name {
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .12em;
  font-size: 16px;
  margin: 0 0 4px;
  color: var(--fg);
}
.thinker-dates {
  color: var(--muted);
  font-size: 11px;
  font-family: ui-monospace, monospace;
  margin: 0 0 4px;
  letter-spacing: .05em;
}
.thinker-tradition {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
  margin: 0;
}

.episode img.waveform {
  width: 100%; display: block;
  background: #f5ecd8;
  border: 1px solid var(--line);
  margin: 4px 0 10px;
}
.episode audio { width: 100%; margin: 4px 0 12px; }

.episode .links { display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 6px; }
.episode .links a {
  display: inline-block;
  padding: 6px 12px;
  border: 1px solid var(--fg);
  color: var(--fg);
  font-size: 12px;
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .12em;
}
.episode .links a:hover { background: var(--fg); color: var(--bg); text-decoration: none; }

.episode .acts {
  margin: 12px 0 4px;
  padding: 0;
  list-style: none;
  color: var(--muted);
  font-size: 13px;
  font-family: ui-monospace, monospace;
}
.episode .acts li { margin: 3px 0; }
.episode .acts li::before { content: "› "; color: var(--kōura); }

details.sources { margin: 14px 0 4px; font-size: 14px; }
details.sources summary {
  cursor: pointer;
  color: var(--kōura);
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .12em;
  font-size: 13px;
}
details.sources ul { margin: 10px 0 0 1.2rem; padding: 0; color: var(--fg); }
details.sources a { color: var(--kōura); }
details.sources .src-note { color: var(--muted); font-style: italic; }

.episode .path {
  margin: 10px 0 0;
  color: var(--muted);
  font-family: ui-monospace, monospace;
  font-size: 11px;
  letter-spacing: .08em;
}

/* Roster grid — 2 up on mobile, auto-fit above */
.roster-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
@media (min-width: 640px) {
  .roster-grid {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 18px;
  }
}

/* Footer */
footer.site-footer {
  padding: 50px 0 40px;
  border-top: 1px solid var(--line);
  background: var(--bg-2);
  margin-top: 30px;
}
.site-footer .row {
  display: flex; flex-wrap: wrap; gap: 30px;
  justify-content: space-between; align-items: flex-start;
}
.site-footer h4 {
  color: var(--fg);
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: .18em;
  font-size: 14px;
  margin: 0 0 12px;
}
.site-footer a { color: var(--muted); display: block; margin: 4px 0; }
.site-footer a:hover { color: var(--kōura); text-decoration: none; }
.site-footer .copy { color: var(--muted); font-size: 13px; margin-top: 30px; opacity: .75; }

/* Mobile tuning */
@media (max-width: 700px) {
  body { font-size: 16px; }
  .shell { padding: 0 16px; }
  .hero { padding: 50px 0 40px; }
  .hero h1 { font-size: clamp(38px, 11vw, 60px); }
  .hero .kaupapa { font-size: 16px; }
  section.block { padding: 40px 0; }
  section.block h2 { font-size: 26px; }
  .site-nav .links a { margin-left: 10px; font-size: 12px; }
  .episode { padding: 18px 16px; }
  .episode h3 { font-size: 22px; }
  .episode .meta-row { font-size: 11px; letter-spacing: .06em; gap: 8px; }
  .episode .meta-row .runtime { margin-left: 0; }
  .thinker-name { font-size: 14px; }
  .thinker-dates { font-size: 10px; }
  .thinker-tradition { font-size: 11px; line-height: 1.3; }
  .episode .links { gap: 6px; }
  .episode .links a { padding: 5px 9px; font-size: 11px; }
  details.sources ul { margin-left: 1rem; padding-right: 4px; word-wrap: break-word; overflow-wrap: anywhere; }
  details.sources a { word-break: break-word; }
  footer.site-footer { padding: 40px 0 30px; }
  .site-footer .row { gap: 22px; }
}
""".strip()


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kd-dialogues — audio dialogues from The Kiwi Dialectic</title>
<meta name="description" content="Long-form audio dialogues. Six historical thinkers plus contemporary voices they'd argue with. Full transcripts, sources, and portraits. Made for The Kiwi Dialectic.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700&display=swap">
<style>{css}</style>
</head>
<body>

<nav class="site-nav">
  <div class="shell row">
    <a href="./" class="brand">KD <span>DIALOGUES</span></a>
    <div class="links">
      <a href="#episodes">Episodes</a>
      <a href="#roster">Roster</a>
      <a href="{six_thinkers}">Six Thinkers ↗</a>
      <a href="{substack}">Substack ↗</a>
    </div>
  </div>
</nav>

<header class="hero">
  <div class="shell">
    <p class="eyebrow">Round Two · Audio · The Kiwi Dialectic</p>
    <h1>The Dialogues.<br>Two voices at a time.<br>No music. No ads.</h1>
    <p class="kaupapa">Historical thinkers refitted for the algorithmic century, put in a room with the contemporary voices they'd argue with. Full transcripts, sources, and portraits — CC BY-SA 4.0.</p>
    <div class="ctas">
      <a class="btn kofi" href="{kofi}" target="_blank" rel="noopener">☕ Koha via Ko-fi</a>
      <a class="btn" href="{substack}" target="_blank" rel="noopener">Subscribe on Substack →</a>
      <a class="btn" href="{repo_url}" target="_blank" rel="noopener">Source on GitHub</a>
    </div>
  </div>
</header>

<section class="block" id="episodes">
  <div class="shell">
    <p class="section-eyebrow">Audio Episodes</p>
    <h2>Every dialogue lives here.</h2>
{audio_cards}
  </div>
</section>

<section class="block" id="roster">
  <div class="shell">
    <p class="section-eyebrow">The Roster</p>
    <h2>Voices in the writing room.</h2>
    <div class="roster-grid">
{roster_cards}
    </div>
  </div>
</section>

{video_section}

<footer class="site-footer">
  <div class="shell">
    <div class="row">
      <div>
        <h4>KD DIALOGUES</h4>
        <a href="{repo_url}" target="_blank">GitHub repo (audio lives here)</a>
        <a href="{substack}" target="_blank">The Kiwi Dialectic on Substack</a>
        <a href="{kofi}" target="_blank">Support on Ko-fi</a>
      </div>
      <div>
        <h4>SISTER SITE</h4>
        <a href="{six_thinkers}" target="_blank">Six Thinkers — free HTML courses</a>
        <a href="https://github.com/robertmccallnz/six-thinkers" target="_blank">six-thinkers repo</a>
        <a href="{calendar}" target="_blank">Course calendar</a>
      </div>
      <div>
        <h4>OPEN</h4>
        <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank">CC BY-SA 4.0</a>
        <a href="{repo_url}/blob/main/README.md" target="_blank">README</a>
        <a href="{repo_url}/blob/main/episodes/SCHEMA.md" target="_blank">Episode schema</a>
      </div>
    </div>
    <p class="copy">© The Kiwi Dialectic · Made in Ōtepoti Dunedin · Voices synthesised from documented cadence, vernacular, and delivery. Portraits and text CC BY-SA 4.0. Train the mind. Arm the class.</p>
  </div>
</footer>

</body>
</html>
"""


def render_episode_card(e: dict) -> str:
    slug = e["dir"]
    mp3 = e.get("mp3", "")
    wf = e.get("waveform")
    cast = e.get("cast", [])

    cast_line = " · ".join(c.title() for c in cast)
    runtime = fmt_runtime(e.get("runtime_seconds", 0))
    n_chapters = len(e.get("chapters", []))

    portrait_html = "\n".join(portrait_card(c) for c in cast) if cast else ""

    ep_number = slug.split("-", 1)[0] if slug and slug[:3].isdigit() else ""

    # Audio + transcript live at repo root (outside /docs), so link them via
    # raw.githubusercontent.com. Waveforms are copied into /docs/waveforms/.
    mp3_url = f"{RAW}/episodes/{slug}/{mp3}" if mp3 else ""
    transcript_url = f"{RAW}/episodes/{slug}/transcript.md"

    waveform_html = ""
    waveform_link_html = ""
    if wf:
        copied = copy_waveform(slug, wf)
        if copied:
            waveform_html = f'<img class="waveform" src="{escape(copied)}" alt="Waveform" loading="lazy">'
            waveform_link_html = f'<a href="{escape(copied)}">Waveform PNG</a>'

    acts = e.get("acts") or []
    acts_html = ""
    if acts:
        acts_html = '<ul class="acts">' + "".join(f"<li>{escape(a)}</li>" for a in acts) + "</ul>"

    links_html = f"""    <div class="links">
      <a href="{escape(mp3_url)}" download>Download MP3</a>
      <a href="{escape(transcript_url)}" target="_blank" rel="noopener">Transcript</a>
      {waveform_link_html}
      <a href="{escape(REPO_URL)}/tree/main/episodes/{escape(slug)}" target="_blank" rel="noopener">Repo folder ↗</a>
    </div>"""

    return f"""    <article class="episode" id="{escape(slug)}">
      <div class="meta-row">
        {f'<span>EP {escape(ep_number)}</span>' if ep_number else ''}
        <span>{escape(cast_line)}</span>
        <span>{n_chapters} chapters</span>
        <span class="runtime">{runtime}</span>
      </div>
      <h3>{escape(e.get('title', slug))}</h3>
      <p class="subtitle">{escape(e.get('subtitle', ''))}</p>
      <div class="thinker-strip">
{portrait_html}
      </div>
      {waveform_html}
      <audio controls preload="none">
        <source src="{escape(mp3_url)}" type="audio/mpeg">
        Your browser cannot play this audio. <a href="{escape(mp3_url)}">Download the mp3</a>.
      </audio>
{links_html}
      {acts_html}
      {render_sources(e.get('sources', []))}
      <p class="path">episodes/{escape(slug)}/ · audio served via raw.githubusercontent.com</p>
    </article>"""


def render_video_section(video_entries: list[dict]) -> str:
    if not video_entries:
        return ""
    cards = []
    for e in video_entries:
        vids = e.get("videos", {})
        video_links = " · ".join(
            f'<a href="../dialogues/{escape(e["dir"])}/{escape(path)}">{escape(asp)}</a>'
            for asp, path in vids.items()
        ) or "<em>No videos rendered yet.</em>"
        thinkers = " · ".join(t.title() for t in e.get("thinkers", []))
        cards.append(f"""    <article class="episode">
      <div class="meta-row"><span>{escape(thinkers)}</span><span class="runtime">{int(e.get('runtime_seconds', 0))}s</span></div>
      <h3>{escape(e.get('title', e['dir']))}</h3>
      <p class="subtitle">{escape(e.get('subtitle', ''))}</p>
      <p>{video_links}</p>
      <p class="path">dialogues/{escape(e['dir'])}/</p>
    </article>""")
    body = "\n".join(cards)
    return f"""
<section class="block" id="videos">
  <div class="shell">
    <p class="section-eyebrow">Video Dialogues</p>
    <h2>Round-tables and pencil-sketch shorts.</h2>
{body}
  </div>
</section>
"""


def render_roster() -> str:
    """Every thinker with a portrait + voice.yml, rendered as a card."""
    slugs = sorted(d.name for d in THINKERS.iterdir() if d.is_dir()) if THINKERS.exists() else []
    return "\n".join(portrait_card(s) for s in slugs)


# ---------------- entrypoint ----------------

def render() -> None:
    audio_entries = collect_audio()
    video_entries = collect_videos()

    if audio_entries:
        audio_cards = "\n".join(render_episode_card(e) for e in audio_entries)
    else:
        audio_cards = '    <p style="opacity:.6"><em>No audio episodes yet. Add one under <code>episodes/</code>.</em></p>'

    roster_cards = render_roster()
    video_section = render_video_section(video_entries)

    html = PAGE.format(
        css=CSS,
        audio_cards=audio_cards,
        roster_cards=roster_cards,
        video_section=video_section,
        substack=SUBSTACK,
        kofi=KOFI,
        repo_url=REPO_URL,
        six_thinkers=SIX_THINKERS_URL,
        calendar=CALENDAR,
    )

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  · {len(audio_entries)} audio episode(s)")
    print(f"  · {len(video_entries)} video dialogue(s)")
    print(f"  · portraits copied to {PORTRAITS_OUT}/")


if __name__ == "__main__":
    render()
