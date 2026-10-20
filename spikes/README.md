# Spikes

Throwaway scripts that answer one risky question each. Results are recorded here.

## nemotron_toolcall.py (2026-10-20)

Question: does an NVIDIA Nemotron model on Nebius Token Factory call a tool correctly?

- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`: 5/5 correct
- `nvidia/nemotron-3-super-120b-a12b`: 5/5 correct

Scope: one tool, one argument, temperature 0, five trials. This shows native tool calling works.
It does not show reliability on multi-step or multi-tool workflows. Measure that when the engine exists.
