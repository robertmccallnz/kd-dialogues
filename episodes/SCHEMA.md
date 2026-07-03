# Episode YAML schema

An audio episode is one YAML file. It picks 2–6 thinkers from `thinkers/` and
lays out the dialogue as a sequence of *acts*, each containing *turns*.

```yaml
slug: hegemony-and-mutual-aid          # required, filesystem-safe
title: How do you break a hegemony that feels like weather?
subtitle: Gramsci and Kropotkin in one room, a hundred and forty years apart.
authors: [The Kiwi Dialectic]           # optional; sets the ID3 artist
license: CC BY-SA 4.0                   # optional; embedded in ID3

# Every named voice must exist as thinkers/<slug>/voice.yml + portrait.png.
# 2–6 voices, picked freely per episode.
cast:
  - gramsci
  - kropotkin

# Optional short "cold open" — narrator introduces the problem.
# Uses the `narrator_voice` below.
cold_open: |
  [warm, unhurried] Round one. The problem: hegemony feels like weather.
  Two voices — Antonio Gramsci, Peter Kropotkin — take it from here.
narrator_voice: kore                    # any Gemini TTS voice; see kd/tts.py

# Optional end card, spoken by the narrator.
end_card: |
  [quiet] For The Kiwi Dialectic. Notes at kiwidialectic.substack.com.

# --- The dialogue itself -------------------------------------------------

acts:
  - title: I. Diagnosis
    # Optional per-act cold open; also uses narrator_voice.
    intro: |
      [neutral] Act one. What is the problem, really?
    turns:
      - thinker: gramsci
        say: |
          [deliberate] The problem is not the state. [pauses] The problem
          is what the state has already taught us to want.
      - thinker: kropotkin
        say: |
          [warm] And yet — every village that ever repaired its own road
          was already practising the future you're describing.
      # …as many turns as you like

  - title: II. Disagreement
    intro: |
      [neutral] Act two. Where do they part company?
    turns:
      - thinker: gramsci
        say: |
          [emphatic] Solidarity is not enough if it never contests the
          commanding heights of culture.
      - thinker: kropotkin
        say: |
          [patient] And the commanding heights are not seized. They are
          [pauses] outgrown, by ten thousand small commons.

  - title: III. Proposal
    intro: |
      [neutral] Act three. What is to be done?
    turns:
      - thinker: gramsci
        say: |
          Build the counter-hegemony inside the shell of the old one.
          Schools. Presses. Halls.
      - thinker: kropotkin
        say: |
          Yes — and mutual aid societies. Reading groups. Repair cafés.
          The future rehearses itself in small rooms.
```

## Fields

| Field           | Required | Notes |
|-----------------|----------|-------|
| `slug`          | yes      | Filesystem-safe. Becomes the episode directory name and MP3 filename. |
| `title`         | yes      | Shown in ID3, waveform PNG, and player captions. |
| `subtitle`      | no       | Shown in ID3 comment and waveform PNG. |
| `authors`       | no       | List of strings. First one is the ID3 artist. |
| `license`       | no       | Copied into the ID3 comment. |
| `cast`          | yes      | 2–6 thinker slugs. Each must have `thinkers/<slug>/voice.yml`. |
| `cold_open`     | no       | Spoken by the narrator before act I. |
| `narrator_voice`| no       | Gemini TTS voice for narrator lines. Defaults to `kore`. |
| `end_card`      | no       | Spoken by the narrator after the final act. |
| `acts`          | yes      | 1+ acts. Each has `title`, optional `intro`, and `turns`. |
| `turns[].thinker`| yes     | Any slug present in `cast`. |
| `turns[].say`   | yes      | Text passed to TTS. May include delivery tags like `[pauses]`, `[emphatic]`. |
| `turns[].tail_ms`| no      | Silence after this turn (default 400ms). |

## Output layout

```
episodes/<slug>/
  script.yml                          ← the only file you edit
  audio/                              ← generated per-turn mp3s (cache)
    001-<narrator>-cold-open.mp3
    002-<thinker>-<turn-index>.mp3
    …
  <slug>.mp3                          ← the stitched episode
  <slug>.waveform.png                 ← poster/thumbnail for embeds
  metadata.json                       ← chapters, cast, runtime, ID3 mirror
  transcript.md                       ← optional — set --transcript on render
  embed.html                          ← a copy-paste HTML5 <audio> block
```
