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
from .manifest import profile_fields, validate as validate_manifest
from ..pack.caps import Version, capabilities, widening
from ..pack.digest import tree_digest
from ..pack.workflow import WorkflowError, parse



class RegistryError(Exception):
    pass


@dataclass
class Listing:
    price_usd: float = 0.0
    unit: str = "task"  # "task" | "hour"
    speciality: str = "general"
    payout_email: str = ""  # where the author is paid (a PayPal email for real payouts)
    per_file_cents: int = 0  # metered pricing: extra cents for every file the helper reads (0 = one flat price)
    base_usd: float = 0.0  # metered pricing: the part every answer costs; price_usd is then the most one answer can cost

    @property
    def metered(self) -> bool:
        return self.per_file_cents > 0

    @property
    def max_cents(self) -> int:
        return max(1, round(self.price_usd * 100))

    def cents_for(self, files_read: int) -> int:
        """What one answer costs: the flat price, or base plus a bit per file read, never more than the stated maximum."""
        if not self.metered:
            return self.max_cents
        return max(1, min(self.max_cents, round(self.base_usd * 100) + self.per_file_cents * max(0, files_read)))

    def text(self) -> str:
        if not self.metered:
            return f"{self.max_cents}¢ each"
        return f"{max(1, round(self.base_usd * 100))}¢ + {self.per_file_cents}¢ per file it reads, at most {self.max_cents}¢"


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
    caps: dict = field(default_factory=dict)  # what the pack can do; widening needs a major version
    skills: list = field(default_factory=list)  # concrete skills the author claims, with example questions
    speciality: str = ""
    needs: list = field(default_factory=list)
    limits: list = field(default_factory=list)

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
            wf = parse((pack_dir / "workflow.yaml").read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            raise RegistryError(f"cannot read pack: {e}") from e
        except WorkflowError as e:
            raise RegistryError(f"invalid workflow: {'; '.join(e.problems)}") from e
        problems = validate_manifest(manifest)
        if problems:
            raise RegistryError("pack.yaml cannot be listed: " + "; ".join(problems))
        digest = tree_digest(pack_dir)
        signed = signing.sign(key, "publish", digest)
        rec = PackRecord(manifest["id"], str(manifest["version"]), digest, signed.public_key,
                         signed.signature, manifest["summary"], listing or Listing())
        rec.caps = capabilities(wf)
        for k, v in profile_fields(manifest).items():
            setattr(rec, k, v)
        try:
            new_v = Version.parse(rec.version)
        except ValueError as e:
            raise RegistryError(str(e)) from e
        earlier = [r for r in self.records.values()
                   if r.publisher_key == rec.publisher_key and r.id == rec.id and Version.parse(r.version) < new_v]
        if earlier:
            prev = max(earlier, key=lambda r: Version.parse(r.version))
            reasons = widening(prev.caps, rec.caps) if prev.caps else []
            if reasons and new_v.major <= Version.parse(prev.version).major:
                raise RegistryError(f"{rec.version} widens what the pack can do ({'; '.join(reasons)}); "
                                    "that needs a new major version")
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
