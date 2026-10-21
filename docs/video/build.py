"""Turns scenes.yaml into everything the two videos need that is text:

    python docs/video/build.py

  docs/video/<video>/script.md           the script for reading and reviewing (scenes, what is on screen, what is said, how long)
  docs/video/<video>/voiceover/<id>.txt  one plain text file per scene, to paste into the voice tool one by one
  docs/video/<video>/voiceover/ALL.txt   the whole voice-over in one piece (for a one-take read, if preferred)

Lengths here are estimates from the word count. Once the real audio files exist, `edit.py` measures them and builds the final timeline.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
KINDS = {"animation": "Animation (Claude Design)", "screen": "Screen recording (real console)", "terminal": "Terminal recording (real command)"}


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9'’]+", text))


def clean(vo: str) -> str:
    return re.sub(r"\s+", " ", vo).strip()


def mmss(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def build(key: str, data: dict, voice: dict) -> None:
    out = HERE / key
    (out / "voiceover").mkdir(parents=True, exist_ok=True)
    wpm, speed = voice["words_per_minute"], voice["speed_up"]
    rows, total_raw = [], 0.0
    for s in data["scenes"]:
        vo = clean(s["vo"])
        n = words(vo)
        raw = n / wpm * 60
        total_raw += raw
        (out / "voiceover" / f"{s['id']}.txt").write_text(vo + "\n", encoding="utf-8")
        rows.append((s, vo, n, raw))
    (out / "voiceover" / "ALL.txt").write_text("\n\n".join(r[1] for r in rows) + "\n", encoding="utf-8")
    total_final = total_raw / speed
    lines = [f"# {data['title']}", "",
             f"{data['hackathon']}. One line to remember: **{data['one_line']}**", "",
             f"Estimated voice: {mmss(total_raw)} as read, {mmss(total_final)} after the {speed}x speed-up "
             f"(limit {mmss(voice['limit_seconds'])}). Scene pictures add a short pause between scenes, so expect about "
             f"{mmss(total_final + 1.2 * len(rows))} in total. The real numbers come from the audio files.", "",
             "| Scene | What it is | Voice (est., final) | Words |", "|---|---|---|---|"]
    for s, vo, n, raw in rows:
        lines.append(f"| {s['id']} {s['name']} | {KINDS[s['kind']]} | {raw / speed:.0f}s | {n} |")
    lines.append("")
    for s, vo, n, raw in rows:
        lines += [f"## {s['id']}. {s['name']}", "", f"**{KINDS[s['kind']]}**", "",
                  f"**On screen:** {s['show']}", "", f"**Caption:** {s['caption']}", "", f"**Voice ({n} words):**", "", f"> {vo}", ""]
    (out / "script.md").write_text("\n".join(lines), encoding="utf-8")
    flag = "  OVER THE LIMIT" if total_final + 1.2 * len(rows) > voice["limit_seconds"] else ""
    print(f"{key}: {len(rows)} scenes, {sum(r[2] for r in rows)} words, voice about {mmss(total_final)} final{flag}")


def main() -> int:
    data = yaml.safe_load((HERE / "scenes.yaml").read_text(encoding="utf-8"))
    for key in ("nebius", "paypal"):
        build(key, data[key], data["voice"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
