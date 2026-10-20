"""Run one pack against a vault inside a lens and return a complete, serialisable report.

Shared by the CLI and the web console. It is the Pull-mode path: the pack program runs here, on the
requester's machine, and sees only what the Memory Broker serves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from .engine.flowd import Engine, Model, Outcome
from .engine.journal import Journal
from .guard.result_guard import ResultGuard
from .memory.broker import Lens, MemoryBroker
from .memory.vault import Vault
from .pack.digest import tree_digest
from .pack.workflow import parse


@dataclass
class RunReport:
    pack_id: str
    version: str
    author: str
    digest: str
    lens: dict
    staged: dict
    withheld: list[str]
    steps: list[dict] = field(default_factory=list)
    broker_events: list[dict] = field(default_factory=list)
    records_handed: list[str] = field(default_factory=list)
    outcome: str = ""
    result: Any = None
    reasons: list[str] = field(default_factory=list)
    tokens: int = 0
    journal_entries: int = 0
    journal_head: str = ""
    journal_ok: bool = False
    run_id: str = ""
    proposals_raw: list = field(default_factory=list)


def run_pack(pack_dir: Path, vault: Vault, lens: Lens, model: Model, *, seed: str, cell=None,
             expected_digest: str | None = None, journal_path: Path | None = None,
             run_id: str | None = None) -> RunReport:
    pack_dir = Path(pack_dir)
    digest = tree_digest(pack_dir)
    if expected_digest is not None and digest != expected_digest:
        raise ValueError("pack content does not match the digest that was approved")
    manifest = yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))
    wf = parse((pack_dir / "workflow.yaml").read_text(encoding="utf-8"))
    broker = MemoryBroker(vault, lens, run_seed=seed)
    validator = Draft202012Validator(manifest["result_schema"])
    journal = Journal(journal_path)
    engine = Engine(wf, model=model, broker=broker, guard=ResultGuard(manifest["result_schema"]),
                    journal=journal, cell=cell,
                    checks={"result_matches_schema": lambda i: validator.is_valid(next(iter(i.values()), None))})
    res = engine.run()
    journal.verify()
    staged_ids = set(broker.manifest)
    return RunReport(
        pack_id=manifest["id"], version=str(manifest["version"]), author=manifest["author"], digest=digest,
        lens={"types": sorted(lens.types), "max_sensitivity": lens.max_sensitivity},
        staged=broker.describe(),
        withheld=sorted(r.id for r in vault.all() if r.id not in staged_ids),
        steps=[{**e["data"], "seq": e["seq"], "event": e["kind"]} for e in journal.entries
               if e["kind"] in ("step_started", "step_committed", "model_call", "cell_run", "incident", "model_error")],
        broker_events=[{"kind": ev.kind, "verdict": ev.verdict.value, "detail": ev.detail} for ev in broker.events],
        records_handed=list(broker.reads),
        outcome=res.outcome.value, result=res.result if res.outcome is Outcome.COMPLETE else None,
        reasons=res.reasons, tokens=res.tokens, journal_entries=len(journal.entries),
        journal_head=journal.head, journal_ok=True,
        run_id=run_id or seed, proposals_raw=res.proposals,
    )
