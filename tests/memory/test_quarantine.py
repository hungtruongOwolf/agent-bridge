import pytest

from bridge.memory.broker import Lens, MemoryBroker
from bridge.memory.quarantine import MAX_PROPOSALS, Quarantine, QuarantineError, validate
from bridge.memory.vault import Record, Vault

OK = {"type": "note", "text": "Acme renewal is at risk this quarter"}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_valid_proposal_passes():
    good, problems = validate([OK])
    assert good == [OK] and problems == []


@pytest.mark.parametrize("bad", [
    {"type": "finance", "text": "x"},                       # type not allowed
    {"type": "note", "text": ""},                           # empty
    {"type": "note", "text": "x" * 201},                    # too long
    {"type": "note", "text": "see https://evil.example/a?d=secret"},  # link = exfil channel
    {"type": "note", "text": "![img](http://x)"},           # markdown image
    {"type": "note", "text": "hi\x00there"},                # control char
    {"type": "note", "text": "ok", "extra": "field"},       # extra field
    {"type": "note"},                                       # missing field
    "just a string",
])
def test_bad_proposals_are_dropped_not_repaired(bad):
    good, problems = validate([bad])
    assert good == [] and len(problems) == 1


def test_only_three_proposals_accepted():
    good, problems = validate([OK] * 5)
    assert len(good) == MAX_PROPOSALS and any("more than" in p for p in problems)


def test_not_a_list_rejected():
    assert validate({"type": "note"})[1] == ["proposals must be a list"]


def test_pending_then_accept_adds_a_tier_1_record_with_origin():
    q, v = Quarantine(), Vault()
    (p,), _ = q.add("run-abc123", "sha256:d1", [OK])
    rec = q.accept(p.id, v)
    assert v.get(rec.id).trust_tier == 1 and v.get(rec.id).sensitivity == "low"
    assert rec.origin == {"pack_digest": "sha256:d1", "run_id": "run-abc123", "proposal_id": p.id}
    assert q.items[p.id].status == "accepted" and q.pending() == []


def test_reject_discards_and_cannot_be_accepted_later():
    q, v = Quarantine(), Vault()
    (p,), _ = q.add("r1", "d", [OK])
    q.reject(p.id)
    with pytest.raises(QuarantineError):
        q.accept(p.id, v)
    assert v.all() == []


def test_double_accept_refused():
    q, v = Quarantine(), Vault()
    (p,), _ = q.add("r1", "d", [OK])
    q.accept(p.id, v)
    with pytest.raises(QuarantineError):
        q.accept(p.id, v)


def test_expiry():
    c = Clock()
    q = Quarantine(ttl_s=100, clock=c)
    (p,), _ = q.add("r1", "d", [OK])
    c.t += 101
    assert q.pending() == [] and q.items[p.id].status == "expired"
    with pytest.raises(QuarantineError):
        q.accept(p.id, Vault())


def test_quarantine_has_a_cap():
    q = Quarantine(max_pending=2)
    added, problems = q.add("r1", "d", [OK, OK, OK])
    assert len(added) == 2 and any("full" in p for p in problems)


def test_revert_run_removes_only_that_runs_records():
    q = Quarantine()
    v = Vault([Record("mine", "note", "low", "written by the user")])
    (a,), _ = q.add("run-A00001", "d", [OK])
    (b,), _ = q.add("run-B00002", "d", [{"type": "fact", "text": "other run"}])
    (c,), _ = q.add("run-A00001", "d", [{"type": "note", "text": "still pending"}])
    ra, rb = q.accept(a.id, v), q.accept(b.id, v)
    out = q.revert_run("run-A00001", v)
    assert out == {"dropped_pending": 1, "removed_from_vault": 1}
    assert v.get(ra.id) is None and v.get(rb.id) is not None and v.get("mine") is not None
    assert q.items[c.id].status == "reverted"


def test_quarantined_text_is_never_served_to_a_pack():
    q, v = Quarantine(), Vault([Record("n1", "note", "low", "sales pipeline notes")])
    q.add("r1", "d", [{"type": "note", "text": "sales secret pending item"}])
    b = MemoryBroker(v, Lens(types=frozenset({"note"})), run_seed="s")
    texts = " ".join(r["text"] for r in b.search("sales secret pending").records)
    assert "pending item" not in texts  # still in Q, so invisible to the broker


def test_accepted_record_is_served_and_marked_as_foreign():
    q, v = Quarantine(), Vault()
    (p,), _ = q.add("run-xyz999", "d", [OK])
    q.accept(p.id, v)
    b = MemoryBroker(v, Lens(types=frozenset({"note"})), run_seed="s")
    recs = b.search("Acme renewal").records
    assert recs and recs[0]["trust"] == "endorsed-foreign"
