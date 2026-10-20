import dataclasses

import pytest

from bridge.pack import signing

D = "sha256:" + "ab" * 32


def test_round_trip():
    k = signing.generate_key()
    s = signing.sign(k, "publish", D)
    assert signing.verify(s, purpose="publish", digest=D, trusted_keys={s.public_key})


def test_untrusted_key_rejected():
    s = signing.sign(signing.generate_key(), "publish", D)
    other = signing.public_b64(signing.generate_key())
    assert not signing.verify(s, purpose="publish", digest=D, trusted_keys={other})


def test_wrong_digest_rejected():
    s = signing.sign(signing.generate_key(), "publish", D)
    assert not signing.verify(s, purpose="publish", digest="sha256:" + "cd" * 32, trusted_keys={s.public_key})


def test_purpose_cannot_be_replayed():
    s = signing.sign(signing.generate_key(), "publish", D)
    assert not signing.verify(s, purpose="attest", digest=D, trusted_keys={s.public_key})
    forged = dataclasses.replace(s, purpose="attest")
    assert not signing.verify(forged, purpose="attest", digest=D, trusted_keys={s.public_key})


def test_tampered_signature_rejected():
    s = signing.sign(signing.generate_key(), "publish", D)
    bad = dataclasses.replace(s, signature=s.signature[:-4] + "AAAA")
    assert not signing.verify(bad, purpose="publish", digest=D, trusted_keys={s.public_key})


def test_garbage_signature_does_not_raise():
    s = signing.sign(signing.generate_key(), "publish", D)
    bad = dataclasses.replace(s, signature="not base64!!")
    assert not signing.verify(bad, purpose="publish", digest=D, trusted_keys={s.public_key})


def test_unknown_purpose_refused():
    with pytest.raises(ValueError):
        signing.sign(signing.generate_key(), "admin", D)
