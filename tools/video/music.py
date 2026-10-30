"""Makes the quiet music bed for the videos, from nothing but sine waves (so there is nothing to license):
a slow pad of chords, a soft bass note, and a gentle arpeggio with an echo.

    python tools/video/music.py nebius|paypal [seconds]      -> video-out/music-<video>.wav

Deterministic: the same call always gives the same file. The edit lowers it under the voice and fades it in and out.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
OUT = Path(__file__).resolve().parents[2] / "video-out"

# chords as semitone offsets from A (nebius: warm and curious, minor to major) and from D (paypal: bright and steady)
THEMES = {
    "nebius": {"root": 57, "bpm": 78, "chords": [(0, [0, 3, 7, 10, 14]), (-4, [0, 4, 7, 11]), (3, [0, 4, 7, 11, 14]), (-2, [0, 4, 7, 9])]},   # Am9 Fmaj7 Cmaj7 G6
    "paypal": {"root": 62, "bpm": 84, "chords": [(0, [0, 4, 7, 11, 14]), (-3, [0, 3, 7, 10, 14]), (5, [0, 4, 7, 11]), (7, [0, 4, 7, 9])]},   # Dmaj9 Bm9 Gmaj7 A6
}


def midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def tone(freq: float, t: np.ndarray, harmonics=((1, 1.0), (2, 0.28), (3, 0.1))) -> np.ndarray:
    return sum(a * np.sin(2 * np.pi * freq * k * t) for k, a in harmonics)


def make(video: str, seconds: float) -> np.ndarray:
    th = THEMES[video]
    n = int(seconds * SR)
    t = np.arange(n) / SR
    beat = 60.0 / th["bpm"]
    bar = beat * 4
    pad = np.zeros(n)
    bass = np.zeros(n)
    arp = np.zeros(n)
    rng = np.random.default_rng(7)
    bars = int(seconds / bar) + 2
    for b in range(bars):
        off, notes = th["chords"][b % len(th["chords"])]
        t0, t1 = b * bar, (b + 1) * bar
        i0, i1 = int(t0 * SR), min(n, int((t1 + 1.2) * SR))                   # each chord rings a little into the next
        if i0 >= n:
            break
        tt = t[i0:i1] - t0
        env = np.minimum(1, tt / 1.4) * np.exp(-np.maximum(0, tt - bar) / 0.6)   # slow swell in, soft release
        for k, semi in enumerate(notes):
            f = midi(th["root"] + off + semi)
            for det in (-0.07, 0.0, 0.07):                                       # three slightly detuned voices make it wide and warm
                pad[i0:i1] += env * 0.05 * tone(f * (1 + det * 0.01), tt, ((1, 1.0), (2, 0.22)))
        bass[i0:i1] += env * 0.14 * np.sin(2 * np.pi * midi(th["root"] + off - 24) * tt)
        for q in range(8):                                                       # arpeggio on the eighth notes
            ta = t0 + q * beat / 2
            ia = int(ta * SR)
            if ia >= n:
                break
            semi = notes[[0, 2, 1, 3, 2, 4 % len(notes), 3, 1][q] % len(notes)] + 12
            tt2 = t[ia:ia + int(1.1 * SR)] - ta
            e = np.exp(-tt2 / 0.28) * np.minimum(1, tt2 / 0.004)
            vel = 0.55 + 0.45 * ((q % 2) == 0) + rng.uniform(-0.05, 0.05)
            arp[ia:ia + len(tt2)] += e * vel * 0.07 * tone(midi(th["root"] + off + semi), tt2, ((1, 1.0), (2, 0.3), (4, 0.08)))
    dry = pad + bass + arp
    # echo: two taps, one to each side, then a little feedback for a sense of space
    L, R = dry.copy(), dry.copy()
    for delay, g, side in ((beat * 0.75, 0.38, "R"), (beat * 1.5, 0.26, "L"), (beat * 2.25, 0.16, "R")):
        d = int(delay * SR)
        (R if side == "R" else L)[d:] += g * arp[:-d] * 1.4
    verb = np.zeros(n)
    for d, g in ((0.071, 0.30), (0.113, 0.24), (0.167, 0.18), (0.231, 0.12)):
        k = int(d * SR)
        verb[k:] += g * (pad + arp)[:-k]
    L, R = L + verb * 0.8, R + np.roll(verb, int(0.011 * SR)) * 0.8
    out = np.stack([L, R], axis=1)
    out /= max(1e-9, np.abs(out).max()) / 0.7
    return out


def main() -> int:
    video = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 215.0
    data = make(video, seconds)
    path = OUT / f"music-{video}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"{path.name}: {seconds:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
