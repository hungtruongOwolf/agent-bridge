#!/bin/sh
# Run inside WSL (Ubuntu) as root: starts dockerd if needed, runs sandbox_probe.py in a locked-down cell.
# Usage: sh sandbox_probe.sh < sandbox_probe.py
set -e
cat > /tmp/sandbox_probe.py
pgrep dockerd >/dev/null || (nohup /usr/bin/dockerd >/tmp/dockerd.log 2>&1 &)
for i in $(seq 1 30); do /usr/bin/docker info >/dev/null 2>&1 && break; sleep 2; done
/usr/bin/docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user 65534:65534 --memory 256m --pids-limit 64 \
  -v /tmp/sandbox_probe.py:/probe.py:ro python:3.12-slim python /probe.py
