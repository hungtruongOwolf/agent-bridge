"""`bridge run`: run a pack against a vault inside the lens the user grants.

    bridge run examples/packs/private-analyst --vault examples/vault.json --types note,contact
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .engine.flowd import Engine, ModelReply, Outcome
from .engine.journal import Journal
from .engine.nebius import NebiusModel, load_api_key
from .engine.tavily import TavilySearch, load_tavily_key
from .guard.result_guard import ResultGuard
from .memory.broker import Lens, MemoryBroker
from .memory.vault import Record, Vault
from .pack.digest import tree_digest
from .sandbox.cell import DockerCell, docker_available
from .pack.workflow import parse
from .hub.certifier import Certifier, sales_dev_suite
from .improve import improve
from .world import open_world, seed as seed_world

ICON = {Outcome.COMPLETE: "OK", Outcome.PARTIAL_BUDGET: "PARTIAL", Outcome.FAILED_PACK: "FAILED", Outcome.FAILED_INFRA: "INFRA-FAILED", Outcome.KILLED: "KILLED"}


class LeakyModel:
    """Simulates a compromised model step that copies everything it sees (deterministic demo)."""

    def complete(self, prompt, inputs):
        dump = json.dumps(inputs, ensure_ascii=False)
        return ModelReply({"summary": dump, "risk": "high"}, tokens=100)


def _check_schema(guard_schema):
    from jsonschema import Draft202012Validator

    v = Draft202012Validator(guard_schema)
    return lambda inputs: v.is_valid(next(iter(inputs.values()), None))


def run(args) -> int:
    pack = Path(args.pack)
    manifest = yaml.safe_load((pack / "pack.yaml").read_text(encoding="utf-8"))
    wf = parse((pack / "workflow.yaml").read_text(encoding="utf-8"))
    vault = Vault([Record(**r) for r in json.loads(Path(args.vault).read_text(encoding="utf-8"))])
    lens = Lens(types=frozenset(args.types.split(",")), max_sensitivity=args.max_sensitivity)
    broker = MemoryBroker(vault, lens, run_seed=args.seed)
    guard = ResultGuard(manifest["result_schema"])

    print(f"pack     {manifest['id']} {manifest['version']} by {manifest['author']}")
    print(f"digest   {tree_digest(pack)[:23]}...")
    d = broker.describe()
    print(f"lens     types={sorted(lens.types)} up to '{lens.max_sensitivity}' -> {d['count']} records staged {d['by_type']}")

    if args.model == "leak":
        model, label = LeakyModel(), "simulated compromised model (copies everything)"
    else:
        model, label = NebiusModel(load_api_key(args.env)), "NVIDIA Nemotron on Nebius"
    print(f"model    {label}\n")

    journal = Journal(Path(args.journal)) if args.journal else Journal()
    engine = Engine(wf, model=model, broker=broker, guard=guard, journal=journal, cell=DockerCell(),
                    web=TavilySearch(load_tavily_key(args.env)) if "web_search" in (pack / "workflow.yaml").read_text(encoding="utf-8") else None,
                    checks={"result_matches_schema": _check_schema(manifest["result_schema"])})
    result = engine.run()

    for e in journal.entries:
        if e["kind"] in ("step_started", "incident"):
            print(f"  {e['kind']:<13} {json.dumps(e['data'], ensure_ascii=False)[:100]}")
    print()
    for ev in broker.events:
        print(f"  broker event  {ev.kind:<15} {ev.verdict.value:<5} {ev.detail}")
    print(f"\nrecords handed to the pack: {broker.reads}")
    print(f"outcome  {ICON[result.outcome]}  tokens={result.tokens}")
    if result.outcome is Outcome.COMPLETE:
        print("result  ", json.dumps(result.result, ensure_ascii=False))
    else:
        print("result   (nothing delivered)", "; ".join(result.reasons))
    journal.verify()
    print(f"journal  {len(journal.entries)} entries, chain verified, head {journal.head[:16]}...")
    return 0 if result.outcome is Outcome.COMPLETE else 2


def seed_cmd(args) -> int:
    world = open_world(args.state)
    model = NebiusModel(load_api_key(args.env))
    seed_world(world, Path(args.packs), model, model.model, cell=DockerCell() if docker_available() else None,
               web=TavilySearch(load_tavily_key(args.env)))
    print(f"\nmarketplace ready in {args.state}/")
    for r in world.market.ranked():
        print(f"  {r.get('rank', '-'):>2}  {r['status']:<11} {r['id']:<17} score={r['score']}  stars={r['stars']}")
    return 0


def serve_cmd(args) -> int:
    from .web.server import App, serve

    world = open_world(args.state)
    app = App(world, Path(args.packs), Path(args.vault), Path(args.env), cell=DockerCell())
    httpd = serve(app, args.port)
    print(f"console on http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _model_and_tools(args, pack: Path):
    model = NebiusModel(load_api_key(args.env))
    uses_web = "web_search" in (pack / "workflow.yaml").read_text(encoding="utf-8")
    return model, DockerCell(), (TavilySearch(load_tavily_key(args.env)) if uses_web else None)


def improve_cmd(args) -> int:
    world = open_world(args.state)
    pack = Path(args.packs) / args.pack
    model, cell, web = _model_and_tools(args, pack)
    dev = Certifier(world.certifier.key, sales_dev_suite(), runs_per_task=3)
    out = Path(args.state) / "candidates" / args.pack
    rep = improve(pack, out, model, dev, cell=cell, web=web)
    print(f"\n{rep.pack_id} {rep.old_version}: baseline {rep.baseline.passes}/{rep.baseline.total} "
          f"(score {rep.baseline.score}) on the development suite")
    for i, v in enumerate(rep.variants):
        tag = "REJECTED: " + v.rejected if v.rejected else f"{v.passes}/{v.total} score {v.score}"
        print(f"  variant {i + 1}: {tag}{'   <- chosen' if rep.chosen == i else ''}")
    print(f"\n{rep.note}")
    if rep.diff:
        print(f"candidate {rep.new_version} in {rep.out_dir}")
        print(f"typed diff: prompt_only={rep.diff['prompt_only']} widened={rep.diff['widened']} "
              f"changed_steps={[c['step'] for c in rep.diff['prompt_changes']]}")
        print(f"to publish it: bridge approve {args.pack} --state {args.state}")
    return 0 if rep.diff else 3


def approve_cmd(args) -> int:
    world = open_world(args.state)
    cand = Path(args.state) / "candidates" / args.pack
    if not cand.exists():
        print("no candidate to approve; run `bridge improve` first")
        return 2
    prev = [r for r in world.registry.records.values() if r.id == yaml.safe_load((cand / "pack.yaml").read_text(encoding="utf-8"))["id"]]
    listing = prev[0].listing if prev else None
    rec = world.registry.publish(cand, world.author_key, listing)
    model, cell, web = _model_and_tools(args, cand)
    att = world.certifier.certify(cand, model, model.model, cell=cell, web=web)
    world.market.add_attestation(att)
    print(f"published {rec.key}")
    for r in sorted((r for r in world.registry.records.values() if r.id == rec.id), key=lambda r: r.version):
        a = world.market._atts.get(r.digest)
        print(f"  {r.version}: held-out {a.passes}/{a.total} score {a.score}" if a else f"  {r.version}: not certified")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a pack against a vault inside a lens")
    r.add_argument("pack")
    r.add_argument("--vault", required=True)
    r.add_argument("--types", required=True, help="comma-separated record types the pack may read")
    r.add_argument("--max-sensitivity", default="medium", choices=["low", "medium", "high"])
    r.add_argument("--model", default="nebius", choices=["nebius", "leak"])
    r.add_argument("--env", default=".env")
    r.add_argument("--seed", default="demo-run-1")
    r.add_argument("--journal", help="write the run journal to this file")
    r.set_defaults(fn=run)
    sd = sub.add_parser("seed", help="publish the example packs and have the Certifier evaluate them")
    sd.add_argument("--packs", default="examples/packs")
    sd.add_argument("--state", default=".bridge")
    sd.add_argument("--env", default=".env")
    sd.set_defaults(fn=seed_cmd)
    im = sub.add_parser("improve", help="propose better instructions for a pack and measure them on the dev suite")
    im.add_argument("pack")
    im.add_argument("--packs", default="examples/packs")
    im.add_argument("--state", default=".bridge")
    im.add_argument("--env", default=".env")
    im.set_defaults(fn=improve_cmd)
    ap2 = sub.add_parser("approve", help="owner approval: publish the improved candidate and certify it on the held-out suite")
    ap2.add_argument("pack")
    ap2.add_argument("--state", default=".bridge")
    ap2.add_argument("--env", default=".env")
    ap2.set_defaults(fn=approve_cmd)
    sv = sub.add_parser("serve", help="start the local web console")
    sv.add_argument("--packs", default="examples/packs")
    sv.add_argument("--vault", default="examples/vault.json")
    sv.add_argument("--state", default=".bridge")
    sv.add_argument("--env", default=".env")
    sv.add_argument("--port", type=int, default=8787)
    sv.set_defaults(fn=serve_cmd)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
