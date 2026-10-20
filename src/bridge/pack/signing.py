"""Ed25519 signatures over (kind, digest) statements.

A signed statement is bound to a purpose string, so a signature made for one purpose
(an author publishing a pack) cannot be replayed as another (a Certifier attestation).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PURPOSES = ("publish", "attest")


@dataclass(frozen=True)
class Signed:
    purpose: str
    digest: str
    public_key: str  # base64 raw Ed25519 public key
    signature: str  # base64


def _message(purpose: str, digest: str) -> bytes:
    if purpose not in PURPOSES:
        raise ValueError(f"unknown purpose {purpose!r}")
    return f"agent-bridge/v1\n{purpose}\n{digest}".encode()


def generate_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def public_b64(key: Ed25519PrivateKey | Ed25519PublicKey) -> str:
    pub = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def sign(key: Ed25519PrivateKey, purpose: str, digest: str) -> Signed:
    sig = key.sign(_message(purpose, digest))
    return Signed(purpose, digest, public_b64(key), base64.b64encode(sig).decode())


def verify(signed: Signed, *, purpose: str, digest: str, trusted_keys: set[str]) -> bool:
    """True only if the signature is valid for this purpose and digest AND the key is trusted."""
    if signed.purpose != purpose or signed.digest != digest:
        return False
    if signed.public_key not in trusted_keys:
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(signed.public_key))
        pub.verify(base64.b64decode(signed.signature), _message(purpose, digest))
    except (InvalidSignature, ValueError):
        return False
    return True
