"""Runs a real command and keeps what it printed, with the time each piece appeared, so the terminal scene can replay it faithfully.

    python tools/video/capture_terminal.py video-out/term-n06.json "bridge run examples/packs/exfil-kit ..." ["the command that is actually run"]

The command is shown as typed; what it prints is exactly what it printed. Pieces are stored per line, or per character for
output that has no line breaks (the dots pytest prints while it works)."""
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

out, shown = Path(sys.argv[1]), sys.argv[2]
actual = sys.argv[3] if len(sys.argv) > 3 else shown
start = time.time()
p = subprocess.Popen([a.strip('"') for a in shlex.split(actual, posix=False)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
events, buf, last = [], b"", start
while True:
    ch = p.stdout.read(1)
    if not ch:
        break
    buf += ch
    now = time.time()
    if ch == b"\n":
        events.append({"t": round(now - start, 3), "text": buf.decode("utf-8", "replace")})
        buf = b""
    elif now - last > 0 or True:
        pass
    last = now
    if ch != b"\n" and len(buf) == 1 and ch in b".FEsx":  # a progress mark with no line break yet
        events.append({"t": round(now - start, 3), "text": ch.decode()})
        buf = b""
if buf:
    events.append({"t": round(time.time() - start, 3), "text": buf.decode("utf-8", "replace")})
p.wait()
out.write_text(json.dumps({"cmd": shown, "total": round(time.time() - start, 3), "exit": p.returncode, "events": events}, indent=1), encoding="utf-8")
print(f"captured {len(events)} pieces in {time.time() - start:.1f}s, exit {p.returncode} -> {out}")
