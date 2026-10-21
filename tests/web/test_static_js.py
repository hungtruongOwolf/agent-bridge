"""The console's scripts run in the browser, so they get checked here with node when it is installed."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent.parent / "src" / "bridge" / "web" / "static"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

@pytest.mark.parametrize("name", ["chat.js", "office.js", "story.js", "app.js", "market.js", "memory.js", "studio.js"])
def test_every_script_is_valid_javascript(name):
    r = subprocess.run([NODE, "--check", str(STATIC / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
