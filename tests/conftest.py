import pytest

from bridge.sandbox.cell import CellResult


class FakeCell:
    """Stands in for the Docker Cell in fast tests. Pretends to run `code` steps and, like the real
    in-cell sensor, reports the probes a script contains. Real isolation is tested in tests/sandbox."""

    def run(self, script, inputs):
        attempts = []
        if "socket" in script:
            attempts += ["dns:collector.example.net", "network:('collector.example.net', 443)"]
        if "subprocess" in script:
            attempts.append("process:subprocess.Popen")
        if "/etc/cron" in script:
            attempts.append("write:/etc/cron.d/persist")
        n = len(inputs.get("read", []))
        return CellResult(True, value={"summary": "Analysed %d records." % n, "risk": "medium"}, attempts=attempts)


@pytest.fixture
def fake_cell():
    return FakeCell()


class FakeWeb:
    def __init__(self):
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return [{"title": "SaaS renewals slow in 2026", "url": "https://example.com/a", "snippet": "budget cuts raise churn"}]


class SmartModel:
    """A model that answers the sales-risk suite correctly: names the accounts whose notes say at risk."""

    NAMES = ("Acme", "Globex", "Initech", "Hooli", "Umbrella", "Wayne")

    def complete(self, prompt, inputs):
        from bridge.engine.flowd import ModelReply
        recs = inputs.get("read", [])
        flagged = [r["text"] for r in recs if any(w in r["text"].lower() for w in ("at risk", "frozen", "cut"))]
        names = [n for n in self.NAMES if any(n in t for t in flagged)]
        if not names:
            return ModelReply({"summary": "All accounts look healthy.", "risk": "low"}, tokens=5)
        return ModelReply({"summary": "Accounts at risk: " + ", ".join(names) + ".", "risk": "high"}, tokens=5)
