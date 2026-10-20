"""Integration tests: need a reachable container engine (Docker in WSL on this machine)."""
import subprocess

import pytest

from bridge.sandbox.cell import WSL_DOCKER, DockerCell


def engine_available() -> bool:
    try:
        return subprocess.run(WSL_DOCKER + ["version"], capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not engine_available(), reason="no container engine in WSL")


@pytest.fixture(scope="module")
def cell():
    return DockerCell(timeout=40)


def test_code_runs_and_returns_json(cell):
    r = cell.run("result = {'total': sum(inputs['xs'])}", {"xs": [1, 2, 3]})
    assert r.ok and r.value == {"total": 6}


def test_no_network_from_inside(cell):
    script = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=3).close(); r = 'CONNECTED'\n"
        "except OSError as e:\n"
        "    r = 'blocked'\n"
        "result = {'net': r}\n"
    )
    assert cell.run(script, {}).value == {"net": "blocked"}


def test_only_loopback_interface(cell):
    r = cell.run("import os\nresult = {'ifs': sorted(os.listdir('/sys/class/net'))}", {})
    assert r.value == {"ifs": ["lo"]}


def test_filesystem_is_read_only_and_user_is_unprivileged(cell):
    script = (
        "import os\n"
        "try:\n    open('/etc/pwned','w').write('x'); w = 'WROTE'\nexcept OSError:\n    w = 'blocked'\n"
        "result = {'write': w, 'uid': os.getuid()}\n"
    )
    assert cell.run(script, {}).value == {"write": "blocked", "uid": 65534}


IMAGE_ENV = {"GPG_KEY", "HOME", "HOSTNAME", "LANG", "PATH", "PYTHON_SHA256", "PYTHON_VERSION"}


def test_script_sees_only_declared_inputs_and_none_of_our_environment(cell):
    # GPG_KEY is the public Python release-signing key id baked into the image, not ours.
    r = cell.run("import os\nresult = {'keys': sorted(inputs), 'env': sorted(os.environ)}", {"a": 1})
    assert r.value["keys"] == ["a"]
    assert set(r.value["env"]) <= IMAGE_ENV


def test_infinite_loop_is_killed_on_timeout():
    c = DockerCell(timeout=6)
    r = c.run("while True: pass\nresult = {}", {})
    assert not r.ok and r.timed_out


def test_crash_is_reported_not_raised(cell):
    r = cell.run("raise RuntimeError('boom')", {})
    assert not r.ok and "boom" in r.error


def test_huge_output_is_refused():
    c = DockerCell(timeout=40, max_output=1000)
    r = c.run("result = {'x': 'a' * 100000}", {})
    assert not r.ok and "larger" in r.error


def test_non_object_result_refused(cell):
    assert not cell.run("result = [1, 2]", {}).ok


def test_sensor_reports_network_process_and_write_attempts(cell):
    script = (
        "import socket, subprocess\n"
        "for f in (lambda: socket.create_connection(('1.1.1.1', 443), timeout=2),\n"
        "          lambda: open('/etc/x', 'w'),\n"
        "          lambda: subprocess.run(['ls'])):\n"
        "    try:\n        f()\n    except Exception:\n        pass\n"
        "result = {'done': True}\n"
    )
    r = cell.run(script, {})
    kinds = {a.split(":", 1)[0] for a in r.attempts}
    assert r.ok and {"network", "dns", "write", "process"} <= kinds


def test_clean_script_reports_no_attempts(cell):
    assert cell.run("result = {'n': len(inputs['xs'])}", {"xs": [1, 2]}).attempts == []


def test_writing_under_tmp_is_not_an_attempt(cell):
    r = cell.run("open('/tmp/scratch.txt', 'w').write('x')\nresult = {}", {})
    assert r.ok and r.attempts == []
