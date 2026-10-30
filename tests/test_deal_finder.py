from pathlib import Path

import pytest
import yaml

from bridge.engine.channel3 import RECORDED_LABEL, Channel3Error, RecordedProducts, WebTools
from bridge.engine.flowd import Engine, ModelReply, Outcome
from bridge.guard.result_guard import ResultGuard
from bridge.hub import pricing
from bridge.hub.certifier import Certifier
from bridge.hub.manifest import validate
from bridge.hub.suites import load_suite
from bridge.memory.broker import Lens, MemoryBroker
from bridge.memory.vault import Vault
from bridge.pack import signing
from bridge.pack.caps import capabilities
from bridge.pack.workflow import WorkflowError, parse
from bridge.world import DEMO_PACKS

PACK = Path(__file__).resolve().parent.parent / "examples" / "packs" / "deal-finder"
WF = (PACK / "workflow.yaml").read_text(encoding="utf-8")
MANIFEST = yaml.safe_load((PACK / "pack.yaml").read_text(encoding="utf-8"))


def fails(text, fragment):
    with pytest.raises(WorkflowError) as e:
        parse(text)
    assert fragment in str(e.value)


class Shopper:
    """Stands in for the model: shortlists the first three products it was handed."""

    def complete(self, prompt, inputs):
        found = inputs.get("find") or []
        return ModelReply({"summary": "Here are some options.", "source": found[0]["source"] if found else RECORDED_LABEL,
                           "shortlist": [{"title": p["title"], "price": f"{p['price']:.2f} {p['currency']}", "merchant": p["merchant"],
                                          "url": p["url"], "reason": "Fits the budget."} for p in found[:3]]}, tokens=5)


def engine(web, task="I want a backpack, budget 80 dollars"):
    return Engine(parse(WF), model=Shopper(), broker=MemoryBroker(Vault([]), Lens(types=frozenset()), run_seed="t"),
                  guard=ResultGuard(MANIFEST["result_schema"]), web=web, task=task,
                  checks={"result_matches_schema": lambda i: True})


def test_pack_manifest_and_workflow_are_valid():
    assert validate(MANIFEST) == []
    assert parse(WF).steps["find"].tool == "product_search"


def test_product_search_is_public_so_it_may_not_read_memory_or_private_steps():
    fails(WF.replace("tools: [product_search], prompt", "tools: [product_search], memory: lens, prompt"), "product_search step is public")
    private = """name: xx
start: m
steps:
  - {id: m, kind: tool, tool: memory_search, tools: [memory_search], memory: lens, prompt: "{task}", next: p}
  - {id: p, kind: tool, tool: product_search, tools: [product_search], reads: [m], next: done}
  - {id: done, kind: return, reads: [p]}
"""
    fails(private, "holds private data")
    fails(private.replace("reads: [m]", "reads: [history]"), "holds private data")


def test_capabilities_declare_web_and_that_the_request_words_are_sent():
    caps = capabilities(parse(WF))
    assert caps["web"] and caps["products"] and caps["web_uses_task"] and not caps["memory_lens"]
    assert "product_search" in caps["tools"]


def test_listing_uses_the_complexity_plan_and_a_web_lookup_is_standard():
    lst = DEMO_PACKS["deal-finder"]
    assert (lst.plan_name, lst.light_cents, lst.standard_cents, lst.deep_cents) == ("complexity", 10, 25, 40)
    facts = pricing.RunFacts(model_calls=1, web_lookups=1)
    assert pricing.tier(facts) == "standard" and pricing.cents_for(lst, facts) == 25


def test_run_uses_the_product_source_and_labels_it():
    eng = engine(WebTools(None, RecordedProducts()))
    res = eng.run()
    assert res.outcome is Outcome.COMPLETE and res.result["source"] == RECORDED_LABEL and len(res.result["shortlist"]) == 3
    ev = [e for e in eng.journal.entries if e["kind"] == "web_search"]
    assert ev and ev[0]["data"]["source"] == RECORDED_LABEL and ev[0]["data"]["query"].startswith("I want a backpack")


def test_a_product_source_failure_is_an_infrastructure_failure_with_a_plain_reason():
    class Down:
        def product_search(self, q):
            raise Channel3Error("Channel3 took too long to answer")

    res = engine(Down(), "backpack").run()
    assert res.outcome is Outcome.FAILED_INFRA and "took too long" in res.reasons[0]


def test_certifier_needs_a_product_source_and_the_shopping_suite_is_checkable():
    suite = load_suite("shopping")
    c = Certifier(signing.generate_key(), suite, runs_per_task=2, suites={"shopping": suite})
    with pytest.raises(ValueError, match="product_search"):
        c.certify(PACK, Shopper(), "m")
    assert len(suite.quality) >= 3 and all(t.goal and t.ask for t in suite.quality)
    att = c.certify(PACK, Shopper(), "m", web=WebTools(None, RecordedProducts()))
    assert att.security == "clean" and att.passes > 0


def test_nothing_found_check_wants_an_empty_shortlist():
    t = {t.name: t for t in load_suite("shopping").quality}["nothing-matches"]
    assert t.check({"summary": "Nothing matched.", "shortlist": [], "source": RECORDED_LABEL})
    assert not t.check({"summary": "x", "shortlist": [{"title": "Invented"}], "source": RECORDED_LABEL})
