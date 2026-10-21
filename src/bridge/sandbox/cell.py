"""Cell: runs untrusted pack code in a container with no network interface.

A `code` step is a small Python leaf. It receives ONLY the JSON inputs its step declared (over
stdin), runs as an unprivileged user on a read-only filesystem with no capabilities and no NIC,
and must leave one JSON object in the variable `result`. It has no memory broker, no model, no
tools, no environment secrets. The only way out is the JSON on stdout, which the engine then
validates like any other step output (size cap here, schema in the Result Guard).

On Windows the container engine runs inside a WSL2 distro (Docker Desktop's engine is not used);
`docker_cmd` is the command prefix that reaches it.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field

BOOT = r"""
import json, sys
sys.dont_write_bytecode = True
attempts = []

def _hook(event, args):
    try:
        if event == "socket.connect":
            attempts.append("network:" + str(args[1]))
        elif event == "socket.getaddrinfo":
            attempts.append("dns:" + str(args[0]))
        elif event in ("subprocess.Popen", "os.system", "os.exec", "os.fork", "os.posix_spawn"):
            attempts.append("process:" + event)
        elif event == "open":
            path, mode = args[0], args[1]
            writing = isinstance(mode, str) and any(ch in mode for ch in "wax+")
            if isinstance(path, str) and writing and not path.startswith("/tmp"):
                attempts.append("write:" + path)
    except Exception:
        pass

payload = json.load(sys.stdin)
g = {"inputs": payload["inputs"]}
code = compile(payload["script"], "<pack>", "exec")
sys.addaudithook(_hook)
try:
    exec(code, g)
    out = json.dumps(g["result"])
finally:
    sys.stdout.write(chr(10) + "@@ATTEMPTS@@" + json.dumps(attempts))
sys.stdout.write(chr(10) + "@@RESULT@@" + out)
"""

WSL_DOCKER = ["wsl", "-d", "Ubuntu-22.04", "-u", "root", "--", "/usr/bin/docker"]


def default_docker_cmd() -> list[str]:
    """How to reach a container engine: BRIDGE_DOCKER if set, WSL on Windows, plain `docker` elsewhere."""
    import os
    import shlex
    import sys

    if os.environ.get("BRIDGE_DOCKER"):
        return shlex.split(os.environ["BRIDGE_DOCKER"])
    return WSL_DOCKER if sys.platform == "win32" else ["docker"]


def docker_available(cmd: list[str] | None = None) -> bool:
    try:
        return subprocess.run((cmd or default_docker_cmd()) + ["version"], capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False
IMAGE = "python:3.12-slim"
BOOT_PATH = "/tmp/bridge_cell_boot.py"


class CellError(Exception):
    pass


@dataclass
class CellResult:
    ok: bool
    value: dict | None = None
    error: str = ""
    timed_out: bool = False
    attempts: list[str] = field(default_factory=list)  # sandbox probes seen by the in-cell sensor


def _attempts(text: str) -> list[str]:
    if "@@ATTEMPTS@@" not in text:
        return []
    raw = text.split("@@ATTEMPTS@@", 1)[1].splitlines()[0]
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(i)[:120] for i in items][:50] if isinstance(items, list) else []


class DockerCell:
    def __init__(self, docker_cmd: list[str] | None = None, *, image: str = IMAGE,
                 memory: str = "256m", pids: int = 64, max_output: int = 65536, timeout: float = 30.0):
        self.docker = docker_cmd or default_docker_cmd()
        self.image, self.memory, self.pids = image, memory, pids
        self.max_output, self.timeout = max_output, timeout
        self._ready = False

    # the boot file is written once into the engine's own filesystem so docker args stay simple
    def _ensure_ready(self) -> None:
        if self._ready:
            return
        prefix = self.docker[:-1] if self.docker[0] == "wsl" else None
        if prefix is not None:
            subprocess.run(prefix + ["sh", "-c", "pgrep dockerd >/dev/null || (nohup /usr/bin/dockerd >/tmp/dockerd.log 2>&1 &)"],
                           check=True, timeout=30)
            subprocess.run(prefix + ["sh", "-c", f"cat > {BOOT_PATH}"], input=BOOT.encode(), check=True, timeout=30)
            for _ in range(30):
                if subprocess.run(self.docker + ["info"], capture_output=True, timeout=30).returncode == 0:
                    break
                subprocess.run(prefix + ["sleep", "2"], timeout=10)
        else:  # native docker: the boot file is written on the host and bind-mounted
            from pathlib import Path
            Path(BOOT_PATH).write_text(BOOT, encoding="utf-8")
        self._ready = True

    def run(self, script: str, inputs: dict) -> CellResult:
        self._ensure_ready()
        name = f"bridge-cell-{uuid.uuid4().hex[:12]}"
        cmd = self.docker + [
            "run", "--rm", "-i", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65534:65534",
            "--memory", self.memory, "--pids-limit", str(self.pids),
            "--tmpfs", "/tmp:size=16m,noexec,nosuid",
            "-v", f"{BOOT_PATH}:/boot.py:ro", self.image, "python", "/boot.py",
        ]
        payload = json.dumps({"script": script, "inputs": inputs}).encode()
        try:
            p = subprocess.run(cmd, input=payload, capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(self.docker + ["kill", name], capture_output=True, timeout=30)
            return CellResult(False, error=f"cell exceeded {self.timeout}s", timed_out=True)
        out = p.stdout[: self.max_output + 1]
        if len(out) > self.max_output:
            return CellResult(False, error=f"cell output larger than {self.max_output} bytes")
        text = out.decode("utf-8", errors="replace")
        attempts = _attempts(text)
        if p.returncode != 0 or "@@RESULT@@" not in text:
            last = (p.stderr.decode("utf-8", errors="replace").strip().splitlines() or ["no output"])[-1]
            return CellResult(False, error=f"cell failed (exit {p.returncode}): {last[:200]}", attempts=attempts)
        try:
            value = json.loads(text.split("@@RESULT@@", 1)[1])
        except json.JSONDecodeError:
            return CellResult(False, error="cell result is not valid JSON", attempts=attempts)
        if not isinstance(value, dict):
            return CellResult(False, error="cell result must be a JSON object", attempts=attempts)
        return CellResult(True, value=value, attempts=attempts)
