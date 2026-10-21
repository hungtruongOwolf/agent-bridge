import pytest

from bridge.hub.pricing import PricingError, RunFacts, cents_for, explain, facts_from_report, tier, validate
from bridge.hub.registry import Listing


def L(**kw):
    return Listing(**validate(kw))


def test_a_flat_plan_costs_the_same_every_time():
    p = L(plan="flat", price_usd=0.4)
    assert cents_for(p, RunFacts()) == cents_for(p, RunFacts(files=30, tokens=90000)) == 40 and p.text() == "40¢ per answer"
    assert not p.metered and not p.subscription and p.max_cents == 40


def test_old_listings_without_a_plan_still_mean_flat_or_per_file():
    assert Listing(price_usd=0.15).plan_name == "flat" and Listing(price_usd=0.5, per_file_cents=5, base_usd=0.05).plan_name == "per_file"
    assert Listing(price_usd=0.5, per_file_cents=5, base_usd=0.05).cents_for(4) == 25  # a bare number of files still works


def test_per_file_is_a_start_plus_a_bit_per_file_never_above_the_maximum():
    p = L(plan="per_file", price_usd=0.5, base_usd=0.05, per_file_cents=5)
    assert [cents_for(p, RunFacts(files=n)) for n in (0, 1, 4, 9, 50)] == [5, 10, 25, 50, 50]
    assert p.metered and p.max_cents == 50 and "per file" in p.text()


def test_per_token_charges_for_the_tokens_the_run_used():
    p = L(plan="per_token", price_usd=0.4, base_usd=0.02, per_1k_tokens_cents=3)
    assert cents_for(p, RunFacts(tokens=0)) == 2
    assert cents_for(p, RunFacts(tokens=1000)) == 5 and cents_for(p, RunFacts(tokens=1001)) == 6  # proportional, rounded up to the next cent
    assert cents_for(p, RunFacts(tokens=900_000)) == 40  # capped at the stated maximum
    assert explain(p, RunFacts(tokens=1830)) == "it used 1,830 tokens" and p.text() == "2¢ + 3¢ per 1,000 tokens, at most 40¢"


@pytest.mark.parametrize("facts,expected", [
    (RunFacts(model_calls=1, files=2), "light"), (RunFacts(model_calls=0), "light"),
    (RunFacts(model_calls=2), "standard"), (RunFacts(model_calls=1, web_lookups=1), "standard"), (RunFacts(model_calls=1, files=4), "standard"),
    (RunFacts(model_calls=3), "deep"), (RunFacts(model_calls=1, code_runs=1), "deep"), (RunFacts(model_calls=1, files=12), "deep"),
])
def test_complexity_is_decided_from_what_the_run_did(facts, expected):
    assert tier(facts) == expected


def test_a_complexity_plan_prices_each_tier_and_holds_the_deepest():
    p = L(plan="complexity", light_cents=10, standard_cents=25, deep_cents=60)
    assert p.max_cents == 60 and p.metered
    assert [cents_for(p, f) for f in (RunFacts(model_calls=1), RunFacts(model_calls=2), RunFacts(model_calls=1, code_runs=1))] == [10, 25, 60]
    assert explain(p, RunFacts(model_calls=2, web_lookups=1, files=3)) == "Standard: 2 thinking steps, 1 web lookup, 3 files read"
    assert p.text() == "10¢ light, 25¢ standard, 60¢ deep"


def test_a_monthly_plan_has_a_fee_and_an_answer_allowance():
    p = L(plan="monthly", monthly_usd=5, included_answers=100)
    assert p.subscription and not p.metered and p.max_cents == 500 and cents_for(p, RunFacts()) == 500
    assert p.text() == "$5.00 a month, up to 100 answers, no automatic renewal"


def test_the_facts_come_from_the_journal_not_from_the_helper():
    class Rep:
        records_handed = ["a", "b", "c"]
        tokens = 2500
        steps = [{"event": "model_call"}, {"event": "web_search"}, {"event": "model_call"}, {"event": "cell_run"}, {"event": "step_started"}]
    assert facts_from_report(Rep()) == RunFacts(files=3, tokens=2500, model_calls=2, web_lookups=1, code_runs=1)


@pytest.mark.parametrize("body", [
    {"plan": "nope"}, {"plan": "flat"}, {"plan": "flat", "price_usd": 0}, {"plan": "flat", "price_usd": 6}, {"plan": "flat", "price_usd": True},
    {"plan": "per_file", "price_usd": 0.5, "per_file_cents": 0}, {"plan": "per_file", "price_usd": 0.5, "per_file_cents": 900},
    {"plan": "per_file", "price_usd": 0.5, "base_usd": 0.9, "per_file_cents": 5},
    {"plan": "per_token", "price_usd": 0.5, "per_1k_tokens_cents": 0}, {"plan": "per_token", "price_usd": 0.5, "per_1k_tokens_cents": 1.5},
    {"plan": "complexity", "light_cents": 30, "standard_cents": 20, "deep_cents": 60}, {"plan": "complexity", "light_cents": 10, "standard_cents": 20},
    {"plan": "complexity", "light_cents": 10, "standard_cents": 20, "deep_cents": 900},
    {"plan": "monthly", "monthly_usd": 0.1, "included_answers": 10}, {"plan": "monthly", "monthly_usd": 80, "included_answers": 10},
    {"plan": "monthly", "monthly_usd": 5, "included_answers": 0}, {"plan": "monthly", "monthly_usd": 5, "included_answers": 5000}, {"plan": "monthly", "monthly_usd": 5},
])
def test_a_plan_that_does_not_add_up_is_refused_in_plain_words(body):
    with pytest.raises(PricingError):
        validate(body)


def test_the_old_form_still_validates():
    assert validate({"price_usd": 0.5, "per_file_cents": 5, "base_usd": 0.05})["plan"] == "per_file"
    assert validate({"price_usd": 0.2})["plan"] == "flat"
