"""Pack improvement loop: propose prompt variants, measure each on a development suite, keep the best.

What it may change: the text of the instruction that produces a pack's result. Nothing else.
Topology, tools, memory scope, budgets and code are never touched, and a candidate that differs in
any of them is thrown away (checked by a typed diff). Variants are scored on a PUBLIC development
suite; the held-out suite that produces published scores is used only after the owner approves the
candidate (see `approve` in cli.py), so a pack cannot simply learn the test.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .engine.flowd import Model
from .hub.certifier import Certifier, Suite
from .memory.broker import Lens
from .memory.vault import Vault
from .pack.caps import capabilities, widening
from .pack.workflow import Workflow, parse
from .runner import run_pack


def workflow_diff(old: Workflow, new: Workflow) -> dict:
    """Typed difference between two workflows: what text changed and whether anything else did."""
    changes, other = [], []
    if set(old.steps) != set(new.steps):
        other.append("steps added or removed")
    for sid in sorted(set(old.steps) & set(new.steps)):
        a, b = old.steps[sid], new.steps[sid]
        for f in ("kind", "next", "on_fail", "tool", "check", "script", "reads", "tools", "memory", "type", "propose"):
            if getattr(a, f) != getattr(b, f):
                other.append(f"{sid}.{f}")
        if a.prompt != b.prompt:
            changes.append({"step": sid, "field": "prompt", "old": a.prompt, "new": b.prompt})
    if old.start != new.start or old.budget != new.budget or old.name != new.name:
        other.append("start, budget or name")
    return {"prompt_changes": changes, "other_changes": other, "prompt_only": not other,
            "widened": widening(capabilities(old), capabilities(new))}


@dataclass
class Variant:
    prompt: str
    score: float = 0.0
    passes: int = 0
    total: int = 0
    security: str = ""
    rejected: str = ""


@dataclass
class ImproveReport:
    pack_id: str
    old_version: str
    new_version: str | None
    step: str
    baseline: Variant
    variants: list[Variant] = field(default_factory=list)
    chosen: int | None = None
    diff: dict | None = None
    out_dir: str | None = None
    note: str = ""


def _bump_patch(version: str) -> str:
    a, b, c = (int(x) for x in version.split("."))
    return f"{a}.{b}.{c + 1}"


def _result_step(wf: Workflow) -> str:
    """The llm step that produces the pack's result: the first read of a return step."""
    for s in wf.steps.values():
        if s.kind == "return" and s.reads and wf.steps[s.reads[0]].kind == "llm":
            return s.reads[0]
    raise ValueError("no llm step feeds a return step")


def _write_pack(src: Path, dst: Path, step: str, prompt: str, version: str) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    wf = yaml.safe_load((src / "workflow.yaml").read_text(encoding="utf-8"))
    for s in wf["steps"]:
        if s["id"] == step:
            s["prompt"] = prompt
    manifest = yaml.safe_load((src / "pack.yaml").read_text(encoding="utf-8"))
    manifest["version"] = version
    (dst / "workflow.yaml").write_bytes(yaml.safe_dump(wf, sort_keys=False, width=100000).encode("utf-8"))
    (dst / "pack.yaml").write_bytes(yaml.safe_dump(manifest, sort_keys=False, width=100000).encode("utf-8"))


def _failures(pack_dir: Path, suite: Suite, model: Model, runs: int) -> list[dict]:
    out = []
    for t in suite.quality:
        for i in range(runs):
            rep = run_pack(pack_dir, Vault(list(t.records)), Lens(types=t.lens_types), model, seed=f"imp-{t.name}-{i}")
            if rep.outcome == "COMPLETE" and t.check(rep.result):
                continue
            out.append({"task_goal": t.goal, "records": [r.text for r in t.records],
                        "answer": rep.result if rep.outcome == "COMPLETE" else f"(no answer: {rep.outcome})"})
            break  # one example per task is enough to steer the rewrite
    return out


def improve(pack_dir: Path, out_dir: Path, model: Model, certifier: Certifier, *, variants: int = 4,
            margin: float = 0.05, cell=None, web=None, log=print) -> ImproveReport:
    pack_dir, out_dir = Path(pack_dir), Path(out_dir)
    manifest = yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))
    old_wf = parse((pack_dir / "workflow.yaml").read_text(encoding="utf-8"))
    step = _result_step(old_wf)
    old_prompt = old_wf.steps[step].prompt or ""
    keys = [k for k in manifest["result_schema"].get("required", []) if k in old_prompt]

    base_att = certifier.certify(pack_dir, model, "improve-baseline", cell=cell, web=web)
    baseline = Variant(old_prompt, base_att.score, base_att.passes, base_att.total, base_att.security)
    report = ImproveReport(manifest["id"], str(manifest["version"]), None, step, baseline)
    log(f"baseline on dev suite: {base_att.passes}/{base_att.total} score {base_att.score}")
    if base_att.security != "clean":
        report.note = "baseline fails the security check; not improving a pack that misbehaves"
        return report

    failures = _failures(pack_dir, certifier.suite, model, 2)
    meta = model.complete(
        "You improve the instruction for ONE step of an automated workflow. Write alternative instructions "
        "that fix the failures while keeping the same job and the same output format.",
        {"current_instruction": old_prompt, "good_answers_do": [t.goal for t in certifier.suite.quality],
         "failures": failures, "how_many": variants,
         "must_keep": f"the reply format: JSON with keys {keys}",
         "answer_format": {"variants": ["new instruction text", "..."]}})
    cands = [v for v in (meta.content.get("variants") or []) if isinstance(v, str)][:variants]

    work = out_dir.parent / f".work-{manifest['id']}"
    new_version = _bump_patch(str(manifest["version"]))
    for text in cands:
        v = Variant(text.strip())
        report.variants.append(v)
        if not (20 <= len(v.prompt) <= 1500) or any(k not in v.prompt for k in keys):
            v.rejected = "does not keep the required output format"
            continue
        _write_pack(pack_dir, work, step, v.prompt, new_version)
        diff = workflow_diff(old_wf, parse((work / "workflow.yaml").read_text(encoding="utf-8")))
        if not diff["prompt_only"] or diff["widened"]:
            v.rejected = "changes more than the instruction text"
            continue
        att = certifier.certify(work, model, "improve-variant", cell=cell, web=web)
        v.score, v.passes, v.total, v.security = att.score, att.passes, att.total, att.security
        log(f"variant {len(report.variants)}: {att.passes}/{att.total} score {att.score}")
    shutil.rmtree(work, ignore_errors=True)

    ok = [(i, v) for i, v in enumerate(report.variants) if not v.rejected and v.security == "clean"]
    best = max(ok, key=lambda t: t[1].score, default=None)
    if best is None or best[1].score < baseline.score + margin:
        report.note = "no variant beat the baseline by the required margin; nothing to publish"
        return report
    report.chosen, report.new_version, report.out_dir = best[0], new_version, str(out_dir)
    _write_pack(pack_dir, out_dir, step, best[1].prompt, new_version)
    report.diff = workflow_diff(old_wf, parse((out_dir / "workflow.yaml").read_text(encoding="utf-8")))
    report.note = "candidate written; the owner must approve it before it is published"
    return report
