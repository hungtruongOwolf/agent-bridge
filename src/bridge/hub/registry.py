"""Registry: where authors publish packs and requesters find them.

Publishing validates the pack (workflow parses, manifest is complete), computes its content digest
and stores a record signed by the author's key. A listing (price, speciality) is a separate record
outside the digest, so changing the price never changes the pack. Versions are write-once:
publishing the same (author key, id, version) twice with different content is refused.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..pack import signing
from ..pack.digest import tree_digest
from ..pack.workflow import WorkflowError, parse

REQUIRED = ("id", "version", "author", "summary", "result_schema")


class RegistryError(Exception):
    pass


@dataclass
class Listing:
    price_usd: float = 0.0
    unit: str = "task"  # "task" | "hour"
    speciality: str = "general"


@dataclass
class PackRecord:
    id: str
    version: str
    digest: str
    publisher_key: str
    signature: str
    summary: str
    listing: Listing = field(default_factory=Listing)
    stars: int = 0
    starred_by: list[str] = field(default_factory=list)
    revoked: str | None = None

    @property
    def key(self) -> str:
        return f"{self.publisher_key[:8]}/{self.id}@{self.version}"


class Registry:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.records: dict[str, PackRecord] = {}
        if self.path and self.path.exists():
            for raw in json.loads(self.path.read_text(encoding="utf-8")):
                raw["listing"] = Listing(**raw["listing"])
                r = PackRecord(**raw)
                self.records[r.key] = r

    def _save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps([asdict(r) for r in self.records.values()], indent=2), encoding="utf-8")

    def publish(self, pack_dir: Path, key: Ed25519PrivateKey, listing: Listing | None = None) -> PackRecord:
        pack_dir = Path(pack_dir)
        try:
            manifest = yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))
            parse((pack_dir / "workflow.yaml").read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            raise RegistryError(f"cannot read pack: {e}") from e
        except WorkflowError as e:
            raise RegistryError(f"invalid workflow: {'; '.join(e.problems)}") from e
        missing = [f for f in REQUIRED if not (manifest or {}).get(f)]
        if missing:
            raise RegistryError(f"pack.yaml is missing: {', '.join(missing)}")
        digest = tree_digest(pack_dir)
        signed = signing.sign(key, "publish", digest)
        rec = PackRecord(manifest["id"], str(manifest["version"]), digest, signed.public_key,
                         signed.signature, manifest["summary"], listing or Listing())
        existing = self.records.get(rec.key)
        if existing and existing.digest != digest:
            raise RegistryError(f"{rec.key} is already published with different content; bump the version")
        if existing:
            rec.stars, rec.starred_by, rec.revoked = existing.stars, existing.starred_by, existing.revoked
        self.records[rec.key] = rec
        self._save()
        return rec

    def verify(self, rec: PackRecord) -> bool:
        s = signing.Signed("publish", rec.digest, rec.publisher_key, rec.signature)
        return signing.verify(s, purpose="publish", digest=rec.digest, trusted_keys={rec.publisher_key})

    def set_listing(self, key: str, listing: Listing) -> None:
        self.records[key].listing = listing  # price lives outside the digest
        self._save()

    def star(self, key: str, user: str) -> int:
        rec = self.records[key]
        if user not in rec.starred_by:  # one star per user
            rec.starred_by.append(user)
            rec.stars = len(rec.starred_by)
            self._save()
        return rec.stars

    def revoke(self, key: str, reason: str) -> None:
        self.records[key].revoked = reason
        self._save()

    def installable(self) -> list[PackRecord]:
        return [r for r in self.records.values() if r.revoked is None and self.verify(r)]
