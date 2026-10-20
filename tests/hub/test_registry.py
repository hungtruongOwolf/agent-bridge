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
