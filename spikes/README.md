# Spikes

Throwaway scripts that answer one risky question each. Results are recorded here.

## nemotron_toolcall.py (2026-10-20)

Question: does an NVIDIA Nemotron model on Nebius Token Factory call a tool correctly?

- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`: 5/5 correct
- `nvidia/nemotron-3-super-120b-a12b`: 5/5 correct

Scope: one tool, one argument, temperature 0, five trials. This shows native tool calling works.
It does not show reliability on multi-step or multi-tool workflows. Measure that when the engine exists.

## sandbox_probe.py / sandbox_probe.sh (2026-10-20)

Question: can a Cell with no network interface run on this machine (Windows 11 Home, WSL2)?

Setup: Docker Engine 29.1.3 installed inside the `Ubuntu-22.04` WSL distro (Docker Desktop's engine
returned HTTP 500 on this machine, so it is not used). Cell flags: `--network none --read-only
--cap-drop ALL --security-opt no-new-privileges --user 65534 --memory 256m --pids-limit 64`.

| Probe (inside the Cell) | `--network none` | control (network on) |
|---|---|---|
| interfaces | `lo` only | `eth0`, `lo` |
| TCP to 1.1.1.1:443 | blocked | connected |
| DNS lookup | blocked | connected |
| write to rootfs | blocked | blocked |
| uid / effective caps | 65534 / 0 | 65534 / 0 |

Scope: this shows the basic no-NIC Cell works. It does not test a malicious pack trying to escape the
sandbox, sleep/wake behavior, the unix-socket exit to the sidecar, or a DNS-exfil sensor (D5).
