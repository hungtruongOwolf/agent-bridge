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
from .hub.certifier import Certifier
from .hub.suites import load_suite
from .improve import improve
from .payments.paypal import PayPalSandbox, load_paypal_credentials
from .payments.provider import ProviderError
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
    ledger, author_email, mode, dashboard = None, "", "test", ""
    if args.payments == "paypal-mock":  # the local practice server stands in for the PayPal sandbox
        import threading
        from .payments.ledger import Ledger
        from .payments.paypal_mock import MOCK_ID, MOCK_SECRET, serve_mock
        mock, _api = serve_mock(args.port + 1, Path(args.state) / "paypal-mock.json")
        threading.Thread(target=mock.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{args.port}"
        ledger = Ledger(PayPalSandbox(MOCK_ID, MOCK_SECRET, base_url=f"http://127.0.0.1:{mock.server_address[1]}",
                                      return_url=base + "/paypal/return", cancel_url=base + "/paypal/cancel"),
                        path=Path(args.state) / "ledger-paypal-mock.json")
        author_email, mode = "author@example.com", "paypal-mock"
        dashboard = f"http://127.0.0.1:{mock.server_address[1]}/mock/state"
        print(f"practice PayPal on http://127.0.0.1:{mock.server_address[1]}/mock/state  (no real money, no real account)")
    if args.payments == "paypal":
        from .payments.ledger import Ledger
        cid, secret = load_paypal_credentials(args.env)
        base = f"http://127.0.0.1:{args.port}"
        ledger = Ledger(PayPalSandbox(cid, secret, return_url=base + "/paypal/return", cancel_url=base + "/paypal/cancel"),
                        path=Path(args.state) / "ledger-paypal.json")
        author_email = next((l.split("=", 1)[1].strip() for l in Path(args.env).read_text(encoding="utf-8").splitlines()
                             if l.startswith("PAYPAL_AUTHOR_EMAIL=")), "")
        mode = "paypal-sandbox"
    app = App(world, Path(args.packs), Path(args.vault), Path(args.env), cell=DockerCell(), ledger=ledger,
              demo_author_email=author_email, payments_mode=mode, payments_dashboard=dashboard)
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
    suite_name = yaml.safe_load((pack / "pack.yaml").read_text(encoding="utf-8")).get("suite") or world.certifier.suite.id
    try:
        dev_suite = load_suite(suite_name + "-dev")  # each held-out suite has a public development twin with different data
    except FileNotFoundError:
        print(f"there is no public development suite named {suite_name}-dev, so this pack cannot be improved yet")
        return 2
    dev = Certifier(world.certifier.key, dev_suite, runs_per_task=3, suites={suite_name: dev_suite})
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


def paypal_mock_cmd(args) -> int:
    from .payments.paypal_mock import MOCK_ID, MOCK_SECRET, serve_mock
    Path(args.state).mkdir(parents=True, exist_ok=True)
    httpd, _ = serve_mock(args.port, Path(args.state) / "paypal-mock.json")
    print(f"practice PayPal on http://127.0.0.1:{httpd.server_address[1]}  client id {MOCK_ID}  secret {MOCK_SECRET}")
    print(f"dashboard: http://127.0.0.1:{httpd.server_address[1]}/mock/state   (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def paypal_check_cmd(args) -> int:
    """Safe live check of the sandbox credentials: get a token and create one $0.01 AUTHORIZE order.
    No money moves: an order does nothing until a buyer approves it, and this command never approves."""
    try:
        cid, secret = load_paypal_credentials(args.env)
        client = PayPalSandbox(cid, secret)
        auth = client.authorize(1, "bridge-paypal-check-1", "bridge-paypal-check")
    except ProviderError as e:
        print(f"PayPal sandbox check FAILED: {e}")
        return 2
    print("PayPal sandbox check OK: credentials accepted, test order created (nothing was charged).")
    print(f"order id: {auth.auth_id}")
    print(f"a buyer would approve it here: {auth.approve_url}")
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
    pc = sub.add_parser("paypal-check", help="verify PayPal sandbox credentials (creates one test order, charges nothing)")
    pc.add_argument("--env", default=".env")
    pc.set_defaults(fn=paypal_check_cmd)
    sv = sub.add_parser("serve", help="start the local web console")
    sv.add_argument("--packs", default="examples/packs")
    sv.add_argument("--vault", default="examples/vault.json")
    sv.add_argument("--state", default=".bridge")
    sv.add_argument("--env", default=".env")
    sv.add_argument("--port", type=int, default=8787)
    sv.add_argument("--payments", choices=["test", "paypal", "paypal-mock"], default="test",
                    help="test = fake money kept in a file; paypal = PayPal sandbox (needs credentials in .env); "
                         "paypal-mock = a local practice server that behaves like the sandbox, with an approval page")
    sv.set_defaults(fn=serve_cmd)
    pm = sub.add_parser("paypal-mock", help="run the local PayPal practice server on its own")
    pm.add_argument("--port", type=int, default=9797)
    pm.add_argument("--state", default=".bridge")
    pm.set_defaults(fn=paypal_mock_cmd)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
