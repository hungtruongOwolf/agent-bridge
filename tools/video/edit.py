"""Builds the finished videos from the pieces (version 2):

    python tools/video/edit.py [nebius|paypal ...] [--speed 1.1] [--no-music]

For every scene: measure its voice file, give the scene that length plus a short lead and tail, make the picture that long
(animations and terminals are rendered to the exact length; recordings are re-timed to it, piece by piece where the story needs it),
slide the caption in, lay the voice on, then join the scenes with short transitions, put a quiet music bed under the voice
(it ducks while the voice speaks) and speed the whole thing up a little. Writes video-out/final/<video>-v2.mp4 and .srt.

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
LEAD, TAIL, TR = 0.5, 0.6, 0.4           # picture before the voice, after it, and the overlap of two scenes (LEAD and TAIL must match anim/fx.js)
PRACTICE = "Practice server that copies PayPal's API. Test money."
NO_CAPTION = {"n01", "n02", "n03", "n07", "n09", "p01", "p02", "p06", "p08"}   # these carry their own words on the picture
NOTES = {"p03": PRACTICE, "p04": PRACTICE, "p05": PRACTICE, "p07": PRACTICE, "n08": "Test money in this demo."}
SRC = {
    "n01": ("anim", "n01"), "n02": ("anim", "n02"), "n03": ("anim", "n03"), "n04": ("rec", "n04"), "n05": ("rec", "n05"),
    "n06": ("rec", "n06"), "n07": ("term", "n07"), "n08": ("rec", "n08"), "n09": ("anim", "n09"),
    "p01": ("anim", "p01"), "p02": ("anim", "p02"), "p03": ("pay", "p03"), "p04": ("pay", "p04"), "p05": ("pay", "p05"),
    "p06": ("anim", "p06"), "p07": ("rec", "p07"), "p08": ("anim", "p08"),
}
# pieces of the long payments recording: (from mark, to mark, speed). The waits and the repeated approval are sped up, the money screens are not.
PAY = {
    "p03": [("p03.start", "p03.end", 1.0)],
    "p04": [("p04.start", "p04.end", 1.0)],
    "p05": [("p05.start", "ask2", 3.0), ("ask2", "back2", 4.0), ("back2", "answer2", 1.0), ("answer2", "nothelp", 1.5), ("nothelp", "p05.end", 2.0)],
}
# recordings with a wait inside: the marks that cut them, and a speed for each piece (None = whatever fits; that is where the model is thinking)
REC = {"n05": (["send", "answer"], [1.0, None, 1.0])}
TRANSITIONS = ["pixelize", "wipeleft", "circleopen", "slideup", "dissolve", "radial", "wiperight", "slideleft"]
ENC = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", "30"]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed:\n{r.stderr[-2500:]}")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def audio_for(video: str, sid: str) -> Path:
    for p in (VIDEO / video / "voiceover" / f"{sid}.mp3", VIDEO / video / f"{sid}.mp3", VIDEO / video / "audio" / f"{sid}.mp3",
              VIDEO / video / "voiceover" / f"{sid}.wav", VIDEO / video / f"{sid}.wav"):
        if p.exists():
            return p
    raise FileNotFoundError(f"no voice file for {sid}")


def marks_of(name: str) -> tuple[float, dict]:
    d = json.loads((OUT / f"rec-{name}.marks.json").read_text())
    return d["duration"], {m["label"]: m["t"] for m in d["marks"]}


def retime(src: Path, pieces: list[tuple[float, float, float | None]], L: float, out: Path) -> str:
    """Cut `src` into pieces (start, end, speed), join them and make the result exactly L seconds: sped up or slowed to fit (never slower than
    0.85x; what is still missing is a hold on the last frame)."""
    fixed = sum((b - a) / sp for a, b, sp in pieces if sp)
    flex = [(a, b) for a, b, sp in pieces if not sp]          # a piece with no speed soaks up what is left, e.g. the wait for the model
    if flex:
        room = max(0.5 * len(flex), L - fixed)
        sp_flex = max(1.0, sum(b - a for a, b in flex) / room)
        pieces = [(a, b, sp or sp_flex) for a, b, sp in pieces]
    t0 = sum((b - a) / sp for a, b, sp in pieces)
    m = t0 / L                                    # above 1: everything is sped up by m; below 0.85: slowed to 0.85 and held at the end
    hold = 0.0
    if m < 0.85:
        hold, m = L - t0 / 0.85, 0.85
    parts, labels = [], []
    for i, (a, b, sp) in enumerate(pieces):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{sp * m:.5f}[p{i}]")
        labels.append(f"[p{i}]")
    vf = ";".join(parts) + (f";{''.join(labels)}concat=n={len(pieces)}:v=1:a=0[j]" if len(pieces) > 1 else ";[p0]null[j]")
    vf += f";[j]fps=30{',tpad=stop_mode=clone:stop_duration=%.3f' % hold if hold > 0.02 else ''}[o]"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-filter_complex", vf, "-map", "[o]", "-t", f"{L:.3f}", "-an", *ENC, str(out)])
    return f"x{m:.2f}" + (f" +hold {hold:.1f}s" if hold > 0.02 else "")


def picture(sid: str, kind: str, name: str, L: float) -> Path:
    """A silent 1920x1080 clip exactly L seconds long."""
    out = OUT / "clips" / f"{sid}-{L:.2f}.mp4"
    out.parent.mkdir(exist_ok=True, parents=True)
    if kind in ("anim", "term"):
        deps = [TOOLS / "anim" / f"{name}.html", TOOLS / "anim" / "fx.js", TOOLS / "anim" / "lib.js", TOOLS / "anim" / "terminal.html"]
        newest = max((p.stat().st_mtime for p in deps if p.exists()), default=0)
        if out.exists() and out.stat().st_mtime > newest:
            return out
    for old in out.parent.glob(f"{sid}-*.mp4"):
        old.unlink()
    if kind in ("anim", "term"):
        page = f"anim/{name}.html" if kind == "anim" else f"anim/terminal.html?scene={name}"
        run(["node", "render.mjs", page, str(out), "--duration", f"{L:.3f}"], cwd=TOOLS)
        return out
    if kind == "rec":
        total, marks = marks_of(name)
        if name in REC:
            cuts = [0.15] + [marks[k] for k in REC[name][0]] + [total]
            pieces = [(cuts[i], cuts[i + 1], REC[name][1][i]) for i in range(len(cuts) - 1)]
        else:
            pieces = [(0.15, total, 1.0)]
        info = retime(OUT / f"rec-{name}.mp4", pieces, L, out)
    else:  # a scene cut out of the long payments recording by its marks
        _, marks = marks_of("pay")
        info = retime(OUT / "rec-pay.mp4", [(marks[a], marks[b], sp) for a, b, sp in PAY[name]], L, out)
    print(f"   {sid}: recording -> {L:.1f}s ({info})")
    return out


def caption_png(sid: str, text: str, note: str = "") -> Path:
    out = OUT / "clips" / f"cap-{sid}.png"
    q = f"anim/caption.html?text={quote(text)}" + (f"&note={quote(note)}" if note else "")
    run(["node", "render.mjs", q, str(out), "--duration", "1", "--still", "0", "--transparent"], cwd=TOOLS)
    return out


def build_scene(video: str, s: dict, L: float, audio: Path) -> Path:
    kind, name = SRC[s["id"]]
    pic = picture(s["id"], kind, name, L)
    out = OUT / "clips" / f"scene-{s['id']}.mp4"
    inputs = ["-i", str(pic)]
    flt = []
    if s["id"] not in NO_CAPTION and s.get("caption"):
        cap = caption_png(s["id"], s["caption"], NOTES.get(s["id"], ""))
        inputs += ["-loop", "1", "-t", f"{L:.3f}", "-i", str(cap)]
        a, z = LEAD + 0.3, L - 0.9
        # the caption rises into place with an ease-out and fades away at the end
        flt.append(f"[1:v]format=rgba,fade=t=in:st={a:.2f}:d=0.35:alpha=1,fade=t=out:st={z:.2f}:d=0.35:alpha=1[c];"
                   f"[0:v][c]overlay=x=0:y='46*pow(1-min(1,max(0,(t-{a:.2f})/0.5)),3)':shortest=1[v]")
        vmap, ai = "[v]", 2
    else:
        vmap, ai = "0:v", 1
    flt.append(f"[{ai}:a]adelay={int(LEAD * 1000)}|{int(LEAD * 1000)},apad=whole_dur={L:.3f},aresample=48000,pan=stereo|c0=c0|c1=c0[a]")
    inputs += ["-i", str(audio)]
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(flt), "-map", vmap, "-map", "[a]", "-t", f"{L:.3f}",
         *ENC, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)])
    return out


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def join(parts: list[Path], lengths: list[float], out: Path, speed: float) -> None:
    """Scenes with a short transition between each, then the whole thing sped up."""
    n = len(parts)
    inputs = [x for p in parts for x in ("-i", str(p))]
    vf, af, cum = [], [], lengths[0]
    cur_v, cur_a = "[0:v]", "[0:a]"
    for i in range(1, n):
        vo, ao = f"[v{i}]", f"[a{i}]"
        vf.append(f"{cur_v}[{i}:v]xfade=transition={TRANSITIONS[(i - 1) % len(TRANSITIONS)]}:duration={TR}:offset={cum - TR:.3f}{vo}")
        af.append(f"{cur_a}[{i}:a]acrossfade=d={TR}:c1=tri:c2=tri{ao}")
        cur_v, cur_a, cum = vo, ao, cum + lengths[i] - TR
    end = cum / speed
    tail = f"{cur_v}setpts=PTS/{speed},fade=t=out:st={end - 0.7:.2f}:d=0.7[V];{cur_a}atempo={speed},afade=t=out:st={end - 0.8:.2f}:d=0.8[A]"
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(vf + af + [tail]), "-map", "[V]", "-map", "[A]", *ENC,
         "-c:a", "aac", "-b:a", "192k", str(out)])


def add_music(video_in: Path, music: Path, out: Path) -> None:
    """Music under the voice: the voice drives a compressor on the music, so it dips whenever someone speaks."""
    total = duration(video_in)
    fc = (f"[1:a]volume=0.55,afade=t=in:st=0:d=2,afade=t=out:st={total - 2.5:.2f}:d=2.5[m];"
          f"[0:a]asplit=2[vo][vk];[m][vk]sidechaincompress=threshold=0.015:ratio=9:attack=25:release=700:makeup=1[md];"
          f"[vo][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[A]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_in), "-i", str(music), "-filter_complex", fc, "-map", "0:v", "-map", "[A]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", str(out)])


def build_video(video: str, data: dict, speed: float, with_music: bool) -> None:
    FINAL.mkdir(exist_ok=True, parents=True)
    print(f"\n== {video}")
    scenes, parts, lengths, srt, start = data["scenes"], [], [], [], 0.0
    for s in scenes:
        audio = audio_for(video, s["id"])
        d = duration(audio)
        L = LEAD + d + TAIL
        print(f" {s['id']} {s['name']}: voice {d:.1f}s, scene {L:.1f}s")
        parts.append(build_scene(video, s, L, audio))
        lengths.append(L)
        text = re.sub(r"\s+", " ", s["vo"]).strip()
        sentences = [x.strip() for x in re.split(r"(?<=[.?!])\s+", text) if x.strip()]
        total = sum(len(x) for x in sentences)
        at = start + LEAD
        for x in sentences:
            span = d * len(x) / total
            srt.append((at, at + span, x))
            at += span
        start += L - TR
    base = FINAL / f"{video}-v2-nomusic.mp4"
    join(parts, lengths, base, speed)
    full = FINAL / f"{video}-v2.mp4"
    music = OUT / f"music-{video}.wav"
    if with_music and music.exists():
        add_music(base, music, full)
    else:
        full.write_bytes(base.read_bytes())
    (FINAL / f"{video}-v2.srt").write_text("\n".join(f"{i + 1}\n{srt_time(a / speed)} --> {srt_time(b / speed)}\n{x}\n" for i, (a, b, x) in enumerate(srt)), encoding="utf-8")
    t = duration(full)
    print(f" -> {full.name}: {t:.1f}s ({int(t // 60)}:{int(t % 60):02d}) at {speed}x" + ("" if t < 180 else "   OVER THREE MINUTES"))


def main() -> int:
    argv = sys.argv[1:]
    speed = float(argv[argv.index("--speed") + 1]) if "--speed" in argv else 1.1
    skip = {"--speed", str(speed), "--no-music"}
    args = [a for a in argv if a not in skip]
    cfg = yaml.safe_load((VIDEO / "scenes.yaml").read_text(encoding="utf-8"))
    for v in (args or ["nebius", "paypal"]):
        build_video(v, cfg[v], speed, "--no-music" not in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
