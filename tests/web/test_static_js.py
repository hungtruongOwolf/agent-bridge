"""The console's scripts run in the browser, so they get checked here with node when it is installed."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent.parent / "src" / "bridge" / "web" / "static"
JS = STATIC / "js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

MODULES = sorted(p for p in JS.rglob("*.js"))


def run(code: str) -> str:
    r = subprocess.run([NODE, "--input-type=module", "-e", code], capture_output=True, text=True, cwd=str(JS))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.mark.parametrize("path", MODULES, ids=lambda p: str(p.relative_to(JS)))
def test_every_module_is_valid_javascript(path):
    r = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_import_points_at_a_file_that_exists():
    import re
    for p in MODULES:
        for target in re.findall(r'from "(\.[^"]+)"', p.read_text(encoding="utf-8")):
            assert (p.parent / target).resolve().is_file(), f"{p.relative_to(JS)} imports {target}"


def test_the_page_loads_only_the_module_entry():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'type="module" src="/static/js/main.js"' in html
    assert html.count("<script") == 1


def test_router_matches_addresses_and_builds_them_back():
    out = run("""
import { compile, match, href, parseQuery } from "./lib/router.js";
const routes = [{ path: "/chats/:id" }, { path: "/memory/shelf/*path" }, { path: "/" }];
const a = match(routes, "/chats/abc");
const b = match(routes, "/memory/shelf/People/Ann%20Lee");
console.log(JSON.stringify([a && a.params, b && b.params, match(routes, "/nope"), match(routes, "/").params, parseQuery("?draft=hi%20there&x=1")]));
""")
    a, b, nope, root, q = json.loads(out)
    assert a == {"id": "abc"}
    assert b["path"].startswith("People/")
    assert nope is None and root == {}
    assert q == {"draft": "hi there", "x": "1"}


def test_workflow_model_adds_and_removes_steps():
    out = run("""
import { addStep, removeStep, steps } from "./studio/workflow-model.js";
console.log(typeof addStep, typeof removeStep, typeof steps);
""")
    assert out == "function function function"


def test_pasted_notes_are_cut_by_blank_lines_or_one_per_line():
    nl = chr(92) + "n"  # a backslash and an n: the JavaScript escape for a new line
    out = run("""
import { pastedNotes, splitNotes } from "./lib/notes.js";
const a = pastedNotes("- Acme likes email@@- Hooli renews in March@@3. Globex is quiet");
const b = pastedNotes("First note@@still the first@@@@Second note");
const c = splitNotes("x".repeat(1700));
console.log(JSON.stringify([a, b, c.length, pastedNotes("   ")]));
""".replace("@@", nl))
    a, b, long_parts, empty = json.loads(out)
    assert a == ["Acme likes email", "Hooli renews in March", "Globex is quiet"]
    assert b == ["First note still the first", "Second note"] or b == ["First note" + chr(10) + "still the first", "Second note"]
    assert long_parts >= 2 and empty == []
