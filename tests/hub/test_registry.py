import dataclasses
import shutil
from pathlib import Path

import pytest

from bridge.hub.registry import Listing, Registry, RegistryError
from bridge.pack import signing

EX = Path(__file__).resolve().parent.parent.parent / "examples" / "packs"


@pytest.fixture
def key():
    return signing.generate_key()


@pytest.fixture
def pack(tmp_path):
    dst = tmp_path / "pack"
    shutil.copytree(EX / "private-analyst", dst)
    return dst


def test_publish_signs_and_verifies(pack, key):
    reg = Registry()
    rec = reg.publish(pack, key, Listing(price_usd=0.5, speciality="sales-analysis"))
    assert rec.digest.startswith("sha256:") and reg.verify(rec)
    assert reg.installable() == [rec]


def test_republish_same_content_is_idempotent(pack, key):
    reg = Registry()
    a = reg.publish(pack, key)
    b = reg.publish(pack, key)
    assert a.key == b.key and len(reg.records) == 1


def test_same_version_different_content_refused(pack, key):
    reg = Registry()
    reg.publish(pack, key)
    (pack / "workflow.yaml").write_bytes((pack / "workflow.yaml").read_bytes() + b"# edited\n")
    with pytest.raises(RegistryError, match="bump the version"):
        reg.publish(pack, key)


def test_price_change_does_not_change_the_digest(pack, key):
    reg = Registry()
    rec = reg.publish(pack, key, Listing(price_usd=1.0))
    reg.set_listing(rec.key, Listing(price_usd=9.0, unit="hour"))
    assert reg.records[rec.key].digest == rec.digest and reg.records[rec.key].listing.price_usd == 9.0


def test_tampered_record_is_not_installable(pack, key):
    reg = Registry()
    rec = reg.publish(pack, key)
    reg.records[rec.key] = dataclasses.replace(rec, digest="sha256:" + "00" * 32)
    assert reg.installable() == []


def test_revoked_pack_is_not_installable(pack, key):
    reg = Registry()
    rec = reg.publish(pack, key)
    reg.revoke(rec.key, "malicious-confirmed")
    assert reg.installable() == []


def test_one_star_per_user(pack, key):
    reg = Registry()
    rec = reg.publish(pack, key)
    reg.star(rec.key, "alice")
    reg.star(rec.key, "alice")
    assert reg.star(rec.key, "bob") == 2


def test_invalid_workflow_refused(pack, key):
    (pack / "workflow.yaml").write_text("name: x\nstart: nope\nsteps: [{id: a, kind: return}]\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="invalid workflow"):
        Registry().publish(pack, key)


def test_incomplete_manifest_refused(pack, key):
    (pack / "pack.yaml").write_text("id: x\nversion: 1\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="missing"):
        Registry().publish(pack, key)


def test_persists_across_restarts(pack, key, tmp_path):
    path = tmp_path / "registry.json"
    rec = Registry(path).publish(pack, key, Listing(price_usd=2.0))
    reg2 = Registry(path)
    assert reg2.records[rec.key].listing.price_usd == 2.0 and reg2.verify(reg2.records[rec.key])


def _bump(pack, version, edit=None):
    text = (pack / "pack.yaml").read_bytes().decode().replace("version: 0.1.0", f"version: {version}")
    (pack / "pack.yaml").write_bytes(text.encode())
    if edit:
        wf = (pack / "workflow.yaml").read_bytes().decode()
        (pack / "workflow.yaml").write_bytes(edit(wf).encode())


def test_prompt_only_update_is_accepted_as_a_minor_or_patch(pack, key):
    reg = Registry()
    reg.publish(pack, key)
    _bump(pack, "0.1.1", lambda w: w.replace("Using only the records", "Using just the records"))
    assert reg.publish(pack, key).version == "0.1.1"


def test_widening_without_a_major_bump_is_refused(pack, key):
    reg = Registry()
    reg.publish(pack, key)
    _bump(pack, "0.2.0", lambda w: w.replace("budget: {tokens: 6000}", "budget: {tokens: 60000}"))
    with pytest.raises(RegistryError, match="major version"):
        reg.publish(pack, key)


def test_widening_with_a_major_bump_is_accepted(pack, key):
    reg = Registry()
    reg.publish(pack, key)
    _bump(pack, "1.0.0", lambda w: w.replace("budget: {tokens: 6000}", "budget: {tokens: 60000}"))
    assert reg.publish(pack, key).caps["budget_tokens"] == 60000


def test_malformed_version_is_refused(pack, key):
    _bump(pack, "banana")
    with pytest.raises(RegistryError, match="1.2.3"):
        Registry().publish(pack, key)


def test_other_publishers_versions_do_not_constrain_this_one(pack, key):
    reg = Registry()
    reg.publish(pack, signing.generate_key())
    _bump(pack, "0.2.0", lambda w: w.replace("budget: {tokens: 6000}", "budget: {tokens: 60000}"))
    assert reg.publish(pack, key).version == "0.2.0"
