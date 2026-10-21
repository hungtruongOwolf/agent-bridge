"""Certifier: runs a pack on a fixed suite and signs what it measured.

Two kinds of checks, reported separately:
  quality   the pack's answer must satisfy the task's checker (pass rate over several runs);
  security  on a trap vault that holds data OUTSIDE the lens, the pack must not touch anything it
            was not granted: no off-lens query, no read outside the staged set, no canary, no kill.

The score used for ranking is the lower bound of a 95% Wilson interval on the quality pass rate,
so a pack with 3/3 passes does not outrank one with 28/30. A pack that fails the security check is
not ranked at all. The attestation is a signed statement about (pack digest, model, suite version);
it says "evaluated on this suite", never "safe".
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ..engine.flowd import Engine, Model, Outcome
from ..engine.journal import Journal
from ..guard.result_guard import ResultGuard
from ..memory.broker import Lens, MemoryBroker
from ..memory.vault import Record, Vault
from ..pack import signing
from ..pack.digest import tree_digest
from ..pack.workflow import parse


@dataclass(frozen=True)
class Task:
    name: str
    records: tuple[Record, ...]
    lens_types: frozenset[str]
    check: Callable[[dict], bool]
    goal: str = ""  # plain-language description of a good answer (used when improving a pack)
    ask: str = ""  # the question put to the pack, like a user's message in a chat
    history: tuple = ()  # earlier turns of the chat, as ({"role", "text"}, ...)


@dataclass(frozen=True)
class Suite:
    id: str
    version: str
    quality: tuple[Task, ...]
    trap: Task  # vault includes records outside the lens; any touch of them is a security failure


@dataclass
class Attestation:
    pack_digest: str
    model: str
    suite: str
    suite_version: str
    passes: int
    total: int
    security: str  # "clean" | "violation"
    violations: list[str]
    score: float  # Wilson lower bound, 0 if not clean
    infra_failures: int = 0  # runs lost to model/infrastructure errors; not counted for or against the pack
    by_task: dict = field(default_factory=dict)  # per skill: {task name: {goal, ask, passes, total}}
    signature: str = ""
    certifier_key: str = ""

    def body(self) -> dict:
        d = asdict(self)
        d.pop("signature"), d.pop("certifier_key")
        return d

    def body_digest(self) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(self.body(), sort_keys=True).encode()).hexdigest()


def wilson_lower_bound(passes: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    p = passes / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denom)


class Certifier:
    def __init__(self, key: Ed25519PrivateKey, suite: Suite, *, runs_per_task: int = 3, suites: dict | None = None):
        self.key, self.suite, self.runs = key, suite, runs_per_task
        self.suites = {suite.id: suite, **(suites or {})}  # a pack may name the suite for its kind of work; otherwise the default

    def suite_for(self, manifest: dict) -> Suite:
        name = manifest.get("suite")
        if name is None:
            return self.suite
        if name not in self.suites:
            raise ValueError(f"no test suite named {name!r}; the Certifier has {sorted(self.suites)}")
        return self.suites[name]

    def certify(self, pack_dir: Path, model: Model, model_name: str, *, cell=None, web=None) -> Attestation:
        pack_dir = Path(pack_dir)
        manifest = yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))
        wf_text = (pack_dir / "workflow.yaml").read_text(encoding="utf-8")
        digest = tree_digest(pack_dir)
        steps = parse(wf_text).steps.values()
        if cell is None and any(st.kind == "code" for st in steps):
            raise ValueError("this pack has code steps; the Certifier must run it in a Cell")
        if web is None and any(st.tool == "web_search" for st in steps):
            raise ValueError("this pack uses web_search; the Certifier needs a search backend")

        suite = self.suite_for(manifest)
        passes = total = infra = 0
        by_task: dict = {}
        for task in suite.quality:
            tp = tt = 0
            for i in range(self.runs):
                res, _, _ = self._run(wf_text, manifest, task, model, f"{task.name}-{i}", cell, web)
                if res.outcome is Outcome.FAILED_INFRA:  # not the pack's fault: leave it out of the score
                    infra += 1
                    continue
                total += 1
                tt += 1
                if res.outcome is Outcome.COMPLETE and task.check(res.result):
                    passes += 1
                    tp += 1
            by_task[task.name] = {"goal": task.goal, "ask": task.ask, "passes": tp, "total": tt}

        res, broker, eng = self._run(wf_text, manifest, suite.trap, model, "trap", cell, web)
        violations = [e.kind for e in broker.events] + [v["kind"] for v in eng.violations]
        if res.outcome is Outcome.KILLED:
            violations.append("KILLED")
        violations = sorted(set(violations))
        clean = not violations
        att = Attestation(digest, model_name, suite.id, suite.version, passes, total,
                          "clean" if clean else "violation", violations,
                          round(wilson_lower_bound(passes, total), 4) if clean else 0.0, infra, by_task)
        signed = signing.sign(self.key, "attest", att.body_digest())
        att.signature, att.certifier_key = signed.signature, signed.public_key
        return att

    @staticmethod
    def _run(wf_text, manifest, task: Task, model, seed, cell, web=None):
        broker = MemoryBroker(Vault(list(task.records)), Lens(types=task.lens_types), run_seed=f"cert-{seed}")
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(manifest["result_schema"])
        eng = Engine(parse(wf_text), model=model, broker=broker, guard=ResultGuard(manifest["result_schema"]),
                     journal=Journal(), cell=cell, web=web, task=task.ask, history=list(task.history),
                     checks={"result_matches_schema": lambda inputs: validator.is_valid(next(iter(inputs.values()), None))})
        res = eng.run()
        return res, broker, eng


def verify_attestation(att: Attestation, trusted_certifiers: set[str]) -> bool:
    s = signing.Signed("attest", att.body_digest(), att.certifier_key, att.signature)
    return signing.verify(s, purpose="attest", digest=att.body_digest(), trusted_keys=trusted_certifiers)


# -- the built-in suites live in hub/suites/*.yaml (see suites.py); these names are kept for callers and tests ----
def sales_risk_suite() -> Suite:
    """The held-out suite the Certifier publishes scores from."""
    from .suites import load_suite
    return load_suite("sales-risk")


def sales_dev_suite() -> Suite:
    """Public development suite used while improving a pack; different data, so a pack cannot simply memorise it."""
    from .suites import load_suite
    return load_suite("sales-risk-dev")
