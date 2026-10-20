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
from dataclasses import dataclass

BOOT = r"""
import json, sys
payload = json.load(sys.stdin)
g = {"inputs": payload["inputs"]}
exec(compile(payload["script"], "<pack>", "exec"), g)
out = json.dumps(g["result"])
sys.stdout.write("\n@@RESULT@@" + out)
"""

WSL_DOCKER = ["wsl", "-d", "Ubuntu-22.04", "-u", "root", "--", "/usr/bin/docker"]
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


class DockerCell:
    def __init__(self, docker_cmd: list[str] | None = None, *, image: str = IMAGE,
                 memory: str = "256m", pids: int = 64, max_output: int = 65536, timeout: float = 30.0):
        self.docker = docker_cmd or WSL_DOCKER
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
        if p.returncode != 0 or "@@RESULT@@" not in text:
            last = (p.stderr.decode("utf-8", errors="replace").strip().splitlines() or ["no output"])[-1]
            return CellResult(False, error=f"cell failed (exit {p.returncode}): {last[:200]}")
        try:
            value = json.loads(text.split("@@RESULT@@", 1)[1])
        except json.JSONDecodeError:
            return CellResult(False, error="cell result is not valid JSON")
        if not isinstance(value, dict):
            return CellResult(False, error="cell result must be a JSON object")
        return CellResult(True, value=value)
