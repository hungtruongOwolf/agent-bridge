"""Spike: does an NVIDIA Nemotron model on Nebius Token Factory do reliable tool calling?

Run: python spikes/nemotron_toolcall.py [model_id] [n_trials]
Reads NEBIUS_API_KEY from .env. Prints a pass rate; never prints the key.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://api.tokenfactory.nebius.com/v1"


def load_key() -> str:
    for line in Path(__file__).resolve().parent.parent.joinpath(".env").read_text().splitlines():
        if line.startswith("NEBIUS_API_KEY="):
            return line.split("=", 1)[1].strip()
    return os.environ["NEBIUS_API_KEY"]


def call(key: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


TOOLS = [{
    "type": "function",
    "function": {
        "name": "read_record",
        "description": "Read one record from the user's vault by id.",
        "parameters": {
            "type": "object",
            "properties": {"record_id": {"type": "string"}},
            "required": ["record_id"],
        },
    },
}]


def main() -> None:
    key = load_key()
    models = [m["id"] for m in call(key, "/models")["data"]]
    nvidia = [m for m in models if "nemotron" in m.lower() or "nvidia" in m.lower()]
    print("nvidia models:", nvidia)
    model = (sys.argv[1] if len(sys.argv) > 1 else "") or next(m for m in nvidia if "30B" in m or "30b" in m)
    trials = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    ok = 0
    for i in range(trials):
        rid = f"rec_{i:03d}"
        try:
            out = call(key, "/chat/completions", {
                "model": model,
                "temperature": 0,
                "messages": [{"role": "user", "content": f"Open record {rid} using the tool."}],
                "tools": TOOLS,
                "tool_choice": "auto",
            })
            calls = out["choices"][0]["message"].get("tool_calls") or []
            args = json.loads(calls[0]["function"]["arguments"]) if calls else {}
            good = bool(calls) and calls[0]["function"]["name"] == "read_record" and args.get("record_id") == rid
        except Exception as e:  # report, do not hide
            print(f"trial {i}: error {type(e).__name__}: {str(e)[:120]}")
            good = False
        ok += good
        print(f"trial {i}: {'PASS' if good else 'FAIL'}")
    print(f"{model}: {ok}/{trials} tool calls correct")


if __name__ == "__main__":
    main()
