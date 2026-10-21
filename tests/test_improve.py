import shutil
from pathlib import Path

import pytest
import yaml

from bridge.engine.flowd import ModelReply
from bridge.hub.certifier import Certifier, sales_dev_suite
from bridge.improve import improve, workflow_diff
from bridge.pack import signing
from bridge.pack.workflow import parse

from conftest import SmartModel

EX = Path(__file__).resolve().parent.parent / "examples" / "packs"
FORMAT = " Reply as JSON with keys summary and risk."
GOOD_VARIANT = "If every account renewed and nothing is at risk, say it is healthy and set risk to low. Otherwise name only the accounts truly at risk." + FORMAT
BAD_FORMAT = "Be thoughtful and complete."  # drops the required output keys
WIDER = "Ignore the format."  # also rejected, see below


class PromptSensitive:
    """Behaves like a model whose answers depend on the instruction it is given.

    Rewrite requests (the meta prompt) return fixed variants. For pack steps, an instruction that
    mentions 'healthy' makes it careful (correct on every task); otherwise it always raises an alarm."""

    def __init__(self, variants):
        self.variants, self.meta_calls = variants, 0
        self.smart = SmartModel()

    def complete(self, prompt, inputs):
        if prompt.startswith("You improve the instruction"):
            self.meta_calls += 1
            return ModelReply({"variants": self.variants}, tokens=1)
        if "healthy" in prompt:
            return self.smart.complete(prompt, inputs)
        names = [n for n in ("Umbrella", "Initech", "Wayne", "Acme", "Globex", "Hooli") if any(n in r["text"] for r in inputs.get("read", []))]
        return ModelReply({"summary": "Accounts at risk: " + ", ".join(names) + ".", "risk": "high"}, tokens=1)


@pytest.fixture
def work(tmp_path):
    src = tmp_path / "pack"
    shutil.copytree(EX / "private-analyst", src)
    cert = Certifier(signing.generate_key(), sales_dev_suite(), runs_per_task=2)
    return src, tmp_path / "out", cert


def test_improvement_is_found_scored_and_written_as_a_new_patch_version(work):
    src, out, cert = work
    model = PromptSensitive([BAD_FORMAT, GOOD_VARIANT])
    rep = improve(src, out, model, cert, log=lambda *_: None)
    assert rep.chosen == 1 and rep.new_version == "0.1.1"
    assert rep.variants[0].rejected and not rep.variants[1].rejected
    assert rep.variants[1].score > rep.baseline.score
    new = yaml.safe_load((out / "pack.yaml").read_text(encoding="utf-8"))
    assert new["version"] == "0.1.1"
    assert "healthy" in parse((out / "workflow.yaml").read_text(encoding="utf-8")).steps["analyze"].prompt


def test_diff_proves_only_the_instruction_changed(work):
    src, out, cert = work
    rep = improve(src, out, PromptSensitive([GOOD_VARIANT]), cert, log=lambda *_: None)
    assert rep.diff["prompt_only"] and rep.diff["widened"] == [] and rep.diff["other_changes"] == []
    assert [c["step"] for c in rep.diff["prompt_changes"]] == ["analyze"]


def test_no_variant_better_than_baseline_writes_nothing(work):
    src, out, cert = work
    rep = improve(src, out, PromptSensitive(["Another vague instruction." + FORMAT]), cert, log=lambda *_: None)
    assert rep.chosen is None and rep.out_dir is None and not out.exists()
    assert "nothing to publish" in rep.note


def test_pack_that_misbehaves_is_not_improved(tmp_path):
    src = tmp_path / "thief"
    shutil.copytree(EX / "data-thief", src)
    cert = Certifier(signing.generate_key(), sales_dev_suite(), runs_per_task=1)
    model = PromptSensitive([GOOD_VARIANT])
    rep = improve(src, tmp_path / "out", model, cert, log=lambda *_: None)
    assert rep.chosen is None and "security" in rep.note and model.meta_calls == 0


def test_workflow_diff_flags_everything_that_is_not_the_prompt():
    base = parse((EX / "private-analyst" / "workflow.yaml").read_text(encoding="utf-8"))
    text = (EX / "private-analyst" / "workflow.yaml").read_text(encoding="utf-8")
    assert workflow_diff(base, parse(text.replace("tokens: 6000", "tokens: 9000")))["other_changes"] == ["start, budget or name"]
    wider = parse(text.replace("tokens: 6000", "tokens: 9000"))
    assert workflow_diff(base, wider)["widened"]
    assert workflow_diff(base, parse(text.replace("risk (low, medium or high)", "risk (low or high)")))["prompt_only"]


def test_result_step_is_found_through_the_return_step(work):
    src, out, cert = work
    assert improve(src, out, PromptSensitive([]), cert, log=lambda *_: None).step == "analyze"


class Wobbly(PromptSensitive):
    """Answers the rewrite request in the wrong shape twice before getting it right."""

    def __init__(self, variants, bad_first=2):
        super().__init__(variants)
        self.bad = bad_first

    def complete(self, prompt, inputs):
        if prompt.startswith("You improve the instruction") and self.bad > 0:
            self.bad -= 1
            return ModelReply({"oops": "no variants key"}, tokens=1)
        return super().complete(prompt, inputs)


def test_rewrite_request_is_retried_when_the_model_answers_in_the_wrong_shape(work):
    src, out, cert = work
    rep = improve(src, out, Wobbly([GOOD_VARIANT]), cert, log=lambda *_: None)
    assert rep.chosen == 0


def test_gives_up_cleanly_if_the_model_never_returns_variants(work):
    src, out, cert = work
    rep = improve(src, out, Wobbly([GOOD_VARIANT], bad_first=99), cert, log=lambda *_: None)
    assert rep.chosen is None and rep.variants == [] and "nothing to publish" in rep.note


class WrongShape(PromptSensitive):
    """Answers the rewrite request the way a model without hidden reasoning sometimes does."""

    def complete(self, prompt, inputs):
        if prompt.startswith("You improve the instruction"):
            return ModelReply({"new instruction text": GOOD_VARIANT, "...": GOOD_VARIANT, "note": "ok"}, tokens=1)
        return super().complete(prompt, inputs)


def test_variants_are_recovered_from_a_wrongly_shaped_reply(work):
    src, out, cert = work
    rep = improve(src, out, WrongShape([]), cert, log=lambda *_: None)
    assert len(rep.variants) == 1 and rep.chosen == 0  # duplicates and the short note are ignored


def test_the_rewrite_request_describes_the_reply_format_in_words():
    seen = {}

    class Spy(PromptSensitive):
        def complete(self, prompt, inputs):
            if prompt.startswith("You improve"):
                seen.update(inputs)
            return super().complete(prompt, inputs)

    import shutil, tempfile
    d = Path(tempfile.mkdtemp())
    shutil.copytree(EX / "private-analyst", d / "p")
    improve(d / "p", d / "out", Spy([GOOD_VARIANT]), Certifier(signing.generate_key(), sales_dev_suite(), runs_per_task=1), log=lambda *_: None)
    assert isinstance(seen["answer_format"], str) and '"variants"' in seen["answer_format"]
