"""Local state for a demo marketplace: keys, registry and attestations under one directory.

`seed` publishes the example packs and has the Certifier evaluate them, so the console has a real,
verifiable ranking to show. Keys are stored raw in the state directory (gitignored); this is a demo
hub, not a key-management design.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .engine.flowd import Model
from .hub.certifier import Certifier, sales_risk_suite
from .hub.market import Marketplace
from .hub.registry import Listing, Registry
from .pack import signing

DEMO_PACKS = {
    "private-analyst": Listing(price_usd=0.40, unit="task", speciality="sales-analysis"),
    "quick-skim": Listing(price_usd=0.15, unit="task", speciality="sales-analysis"),
    "deal-brief": Listing(price_usd=0.60, unit="task", speciality="sales-analysis"),
    "exfil-kit": Listing(price_usd=0.10, unit="task", speciality="sales-analysis"),
    "context-brief": Listing(price_usd=0.80, unit="task", speciality="sales-analysis"),
    "data-thief": Listing(price_usd=0.05, unit="task", speciality="sales-analysis"),
}


def _load_or_create_key(path: Path) -> Ed25519PrivateKey:
    if path.exists():
        return Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    key = signing.generate_key()
    path.write_bytes(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                       serialization.NoEncryption()))
    return key


@dataclass
class World:
    state: Path
    registry: Registry
    market: Marketplace
    author_key: Ed25519PrivateKey
    certifier: Certifier


def open_world(state: Path | str = ".bridge") -> World:
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    author = _load_or_create_key(state / "author.key")
    cert_key = _load_or_create_key(state / "certifier.key")
    registry = Registry(state / "registry.json")
    market = Marketplace(registry, {signing.public_b64(cert_key)}, state / "attestations.json")
    return World(state, registry, market, author, Certifier(cert_key, sales_risk_suite(), runs_per_task=4))


def seed(world: World, packs_dir: Path, model: Model, model_name: str, *, cell=None, web=None, log=print) -> None:
    for name, listing in DEMO_PACKS.items():
        rec = world.registry.publish(Path(packs_dir) / name, world.author_key, listing)
        log(f"published {rec.key}  {rec.digest[:19]}...")
        att = world.certifier.certify(Path(packs_dir) / name, model, model_name, cell=cell, web=web)
        world.market.add_attestation(att)
        log(f"certified {name}: security={att.security} passes={att.passes}/{att.total} score={att.score}")
