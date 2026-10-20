"""Marketplace view: registry records joined with verified Certifier attestations, ranked.

Ranking rules (deliberately simple and explainable):
  1. only packs that are installable (valid author signature, not revoked) are listed;
  2. a pack is "certified" only if it has an attestation whose signature verifies, whose pack digest
     equals the listed digest, and whose security result is clean;
  3. certified packs sort by score (Wilson lower bound of the quality pass rate), then by stars;
  4. a pack that failed the security check is shown as FLAGGED at the bottom, never ranked;
  5. uncertified packs follow certified ones; stars alone never lift a pack above a certified one.
"""
from __future__ import annotations

from .certifier import Attestation, verify_attestation
from .registry import PackRecord, Registry


class MarketError(Exception):
    pass


class Marketplace:
    def __init__(self, registry: Registry, trusted_certifiers: set[str]):
        self.registry = registry
        self.trusted = trusted_certifiers
        self._atts: dict[str, Attestation] = {}  # pack digest -> best verified attestation

    def add_attestation(self, att: Attestation) -> None:
        if not verify_attestation(att, self.trusted):
            raise MarketError("attestation signature is not from a trusted Certifier")
        if not any(r.digest == att.pack_digest for r in self.registry.records.values()):
            raise MarketError("attestation is for a pack digest the registry does not hold")
        current = self._atts.get(att.pack_digest)
        if current is None or att.total >= current.total:  # keep the better-evidenced one
            self._atts[att.pack_digest] = att

    def status(self, rec: PackRecord) -> str:
        att = self._atts.get(rec.digest)
        if att is None:
            return "uncertified"
        return "certified" if att.security == "clean" else "flagged"

    def ranked(self) -> list[dict]:
        rows = []
        for rec in self.registry.installable():
            att = self._atts.get(rec.digest)
            rows.append({
                "key": rec.key, "id": rec.id, "version": rec.version, "summary": rec.summary,
                "price_usd": rec.listing.price_usd, "unit": rec.listing.unit, "speciality": rec.listing.speciality,
                "stars": rec.stars, "status": self.status(rec),
                "score": att.score if att and att.security == "clean" else None,
                "evidence": f"{att.passes}/{att.total} on {att.suite} v{att.suite_version}" if att else None,
                "violations": att.violations if att and att.security != "clean" else [],
                "digest": rec.digest,
            })
        order = {"certified": 0, "uncertified": 1, "flagged": 2}
        rows.sort(key=lambda r: (order[r["status"]], -(r["score"] or 0), -r["stars"], r["key"]))
        for i, r in enumerate(x for x in rows if x["status"] == "certified"):
            r["rank"] = i + 1
        return rows
