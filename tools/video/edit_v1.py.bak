"""Builds the finished videos from the pieces:

    python tools/video/edit.py [nebius|paypal ...] [--speed 1.0]

For every scene: measure its voice file, give the scene that length plus a short lead and tail, make the picture that long
(animations and terminals are rendered to the exact length; recordings are re-timed to it), burn the caption, lay the voice on,
and join the scenes. Writes video-out/final/<video>-v1.mp4 and .srt. `--speed 1.2` speeds the whole result up at the end.

Nothing here invents content: the words are the voice files, the picture is the recordings and animations in video-out/.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "video"
VIDEO = ROOT / "docs" / "video"
OUT = ROOT / "video-out"
FINAL = OUT / "final"
LEAD, TAIL = 0.45, 0.55          # picture before the voice starts, and after it ends
NO_CAPTION = {"n02", "n06", "n09", "n10", "p01", "p08", "p09", "p10"}   # these scenes carry their own words on the picture
PRACTICE = "Practice server that speaks the PayPal API. Test money only."
SRC = {
    "n01": ("anim", "n01"), "n02": ("anim", "n02"), "n03": ("rec", "n03"), "n04": ("rec", "n04"), "n05": ("rec", "n05"), "n06": ("term", "n06"),
    "n07": ("rec", "n07"), "n08": ("rec", "n08"), "n09": ("anim", "n09"), "n10": ("anim", "n10"),
    "p01": ("anim", "p01"), "p02": ("rec", "p02"), "p03": ("pay", "p03"), "p04": ("pay", "p04"), "p05": ("pay", "p05"), "p06": ("pay", "p06"),
    "p07": ("rec", "p07"), "p08": ("anim", "p08"), "p09": ("term", "p09"), "p10": ("anim", "p10"),
}


def run(cmd: list[str], cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed:\n{r.stderr[-1500:]}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def audio_for(video: str, sid: str) -> Path:
    for p in (VIDEO / video / f"{sid}.mp3", VIDEO / video / "audio" / f"{sid}.mp3", VIDEO / video / f"{sid}.wav", VIDEO / video / "audio" / f"{sid}.wav"):
        if p.exists():
            return p
    raise FileNotFoundError(f"no voice file for {sid}")


ENC = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", "30"]


def picture(sid: str, kind: str, name: str, L: float) -> Path:
    """A silent 1920x1080 clip exactly L seconds long."""
    out = OUT / "clips" / f"{sid}-{L:.2f}.mp4"
    out.parent.mkdir(exist_ok=True, parents=True)
    if out.exists():
        return out
    for old in out.parent.glob(f"{sid}-*.mp4"):
        old.unlink()
    if kind in ("anim", "term"):
        page = f"anim/{name}.html" if kind == "anim" else f"anim/terminal.html?scene={name}"
        run(["node", "render.mjs", page, str(out), "--duration", f"{L:.3f}"], cwd=TOOLS)
        return out
    if kind == "rec":
        src, a, b = OUT / f"rec-{name}.mp4", 0.15, json.loads((OUT / f"rec-{name}.marks.json").read_text())["duration"]
    else:  # a scene cut out of the long payments recording by its marks
        marks = {m["label"]: m["t"] for m in json.loads((OUT / "rec-pay.marks.json").read_text())["marks"]}
        src, a, b = OUT / "rec-pay.mp4", marks[f"{name}.start"], marks[f"{name}.end"]
    span = b - a
    speed = span / L                       # above 1 the clip is sped up to fit the voice; below, slowed (down to 0.85) and then held on its last frame
    if speed >= 0.85:
        vf = f"setpts=(PTS-STARTPTS)/{speed:.5f},fps=30"
    else:
        vf = f"setpts=(PTS-STARTPTS)/0.85,fps=30,tpad=stop_mode=clone:stop_duration={L - span / 0.85:.3f}"
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{span:.3f}", "-i", str(src), "-vf", vf, "-t", f"{L:.3f}", "-an", *ENC, str(out)])
    print(f"   {sid}: {span:.1f}s of recording -> {L:.1f}s (x{speed:.2f})")
    return out


def caption_png(sid: str, text: str, note: str = "") -> Path:
    out = OUT / "clips" / f"cap-{sid}.png"
    q = f"anim/caption.html?text={quote(text)}" + (f"&note={quote(note)}" if note else "")
    run(["node", "render.mjs", q, str(out), "--duration", "1", "--still", "0", "--transparent"], cwd=TOOLS)
    return out


def build_scene(video: str, s: dict, L: float, audio: Path, d: float) -> Path:
    kind, name = SRC[s["id"]]
    pic = picture(s["id"], kind, name, L)
    out = OUT / "clips" / f"scene-{s['id']}.mp4"
    inputs = ["-i", str(pic)]
    flt = []
    if s["id"] not in NO_CAPTION:
        note = PRACTICE if kind == "pay" else ""
        cap = caption_png(s["id"], s["caption"], note)
        inputs += ["-loop", "1", "-t", f"{L:.3f}", "-i", str(cap)]
        flt.append(f"[1:v]format=rgba,fade=t=in:st={LEAD + 0.2:.2f}:d=0.35:alpha=1,fade=t=out:st={L - 0.55:.2f}:d=0.35:alpha=1[c];[0:v][c]overlay=0:0:shortest=1[v]")
        vmap = "[v]"
        ai = 2
    else:
        vmap, ai = "0:v", 1
    flt.append(f"[{ai}:a]adelay={int(LEAD * 1000)}|{int(LEAD * 1000)},apad=whole_dur={L:.3f},aresample=48000,pan=stereo|c0=c0|c1=c0[a]")
    inputs += ["-i", str(audio)]
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(flt), "-map", vmap, "-map", "[a]", "-t", f"{L:.3f}",
         *ENC, "-c:a", "aac", "-b:a", "192k", str(out)])
    return out


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build_video(video: str, data: dict, speed: float) -> None:
    FINAL.mkdir(exist_ok=True, parents=True)
    print(f"\n== {video}")
    scenes, parts, srt, t0 = data["scenes"], [], [], 0.0
    for s in scenes:
        audio = audio_for(video, s["id"])
        d = duration(audio)
        L = LEAD + d + TAIL
        print(f" {s['id']} {s['name']}: voice {d:.1f}s, scene {L:.1f}s")
        parts.append(build_scene(video, s, L, audio, d))
        text = re.sub(r"\s+", " ", s["vo"]).strip()
        sentences = [x.strip() for x in re.split(r"(?<=[.?!])\s+", text) if x.strip()]
        total = sum(len(x) for x in sentences)
        at = t0 + LEAD
        for x in sentences:
            span = d * len(x) / total
            srt.append((at, at + span, x))
            at += span
        t0 += L
    lst = OUT / "clips" / f"{video}-list.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    full = FINAL / f"{video}-v1.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if speed != 1.0:
        cmd += ["-filter_complex", f"[0:v]setpts=PTS/{speed}[v];[0:a]atempo={speed}[a]", "-map", "[v]", "-map", "[a]", *ENC, "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c", "copy"]
    run(cmd + [str(full)])
    k = speed if speed != 1.0 else 1.0
    (FINAL / f"{video}-v1.srt").write_text("\n".join(f"{i + 1}\n{srt_time(a / k)} --> {srt_time(b / k)}\n{x}\n" for i, (a, b, x) in enumerate(srt)), encoding="utf-8")
    print(f" -> {full.name}: {duration(full):.1f}s ({int(duration(full) // 60)}:{int(duration(full) % 60):02d})")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    speed = float(sys.argv[sys.argv.index("--speed") + 1]) if "--speed" in sys.argv else 1.0
    if "--speed" in sys.argv:
        args = [a for a in args if a != str(speed)]
    cfg = yaml.safe_load((VIDEO / "scenes.yaml").read_text(encoding="utf-8"))
    for v in (args or ["nebius", "paypal"]):
        build_video(v, cfg[v], speed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
