"""The console's scripts run in the browser, so they get checked here with node when it is installed."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent.parent / "src" / "bridge" / "web" / "static"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

AGENTS = [
    {"key": "k1", "id": "private-analyst", "version": "0.1.0", "status": "certified", "rank": 1, "price_usd": 0.4, "score": 0.76, "summary": "Reads notes"},
    {"key": "k2", "id": "deal-brief", "version": "0.1.1", "status": "certified", "rank": 2, "price_usd": 0.6, "score": 0.55, "summary": "proposes one thing worth remembering"},
    {"key": "k3", "id": "context-brief", "version": "0.1.0", "status": "certified", "rank": 3, "price_usd": 0.8, "score": 0.39, "summary": "Looks up public market trends first (web)"},
    {"key": "k4", "id": "quick-skim", "version": "0.1.0", "status": "certified", "rank": 4, "price_usd": 0.15, "score": 0.39, "summary": "Cheapest option"},
    {"key": "k5", "id": "friendly-helper", "version": "0.1.0", "status": "flagged", "price_usd": 0.05, "summary": "x"},
]


@pytest.mark.parametrize("name", ["intent.js", "office.js", "story.js", "app.js"])
def test_every_script_is_valid_javascript(name):
    r = subprocess.run([NODE, "--check", str(STATIC / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def ask(text, selected=None, wallet=None):
    code = f"""
const {{parseIntent}} = require({json.dumps(str(STATIC / 'intent.js'))});
console.log(JSON.stringify(parseIntent({json.dumps(text)}, {json.dumps(AGENTS)}, {json.dumps({'selected': selected, 'wallet': wallet or {'captured': 10, 'paid_out': 9, 'held': 0}})})));
"""
    out = subprocess.run([NODE, "-e", code], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


@pytest.mark.parametrize("sentence,key", [
    ("hire the best one", "k1"), ("Hire the cheapest please", "k4"), ("I need something that can look up the web", "k3"),
    ("hire deal brief", "k2"), ("pick the one that suggests things to remember", "k2"), ("get me quick skim", "k4"),
])
def test_the_assistant_picks_the_right_helper(sentence, key):
    r = ask(sentence)
    assert r["action"] == "select" and r["agentKey"] == key


def test_the_assistant_never_picks_a_helper_that_was_caught_cheating_by_description():
    for sentence in ("hire the cheapest", "hire the best one", "find me the web one"):
        assert ask(sentence)["agentKey"] != "k5"


def test_saying_start_never_starts_anything_because_money_needs_a_human_press():
    r = ask("start the job now", selected="k1")
    assert r["action"] == "confirm" and "press the green start button yourself" in r["say"].lower()


def test_the_assistant_answers_questions_without_acting():
    assert ask("how many coins do I have")["action"] == "none"
    assert "caught" in ask("who are the cheaters")["say"].lower() and "Friendly Helper" in ask("who are the cheaters")["say"]
    assert ask("what can you do")["action"] == "none"
    assert ask("blah blah")["action"] == "none" and "did not catch" in ask("blah blah")["say"]


def test_replies_use_cents_and_plain_words():
    say = ask("hire the best one")["say"]
    assert "40¢ a job" in say and "trust score 76" in say
    for word in ("broker", "sidecar", "digest", "hash"):
        assert word not in say.lower()
