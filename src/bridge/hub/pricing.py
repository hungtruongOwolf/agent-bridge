"""How a helper charges. The author picks a plan when publishing; the platform measures the run, never the helper.

  flat        one price for every answer;
  per_file    a starting price plus a few cents for every file the helper read, up to a maximum;
  per_token   a starting price plus cents for every 1,000 tokens the run used, up to a maximum;
  complexity  a price for light, standard or deep questions, decided from what the run did (see `tier`);
  monthly     one fee for 30 days and up to N answers, with no automatic renewal.

Whatever the plan, the buyer sees the most one answer can cost BEFORE starting, and the hold is exactly that. Afterwards
the real price is worked out from facts the engine recorded (files handed over, tokens spent, model calls, web lookups,
programs run) and the unused part of the hold goes back. Nothing here trusts a number the helper reports about itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

PLANS = ("flat", "per_file", "per_token", "complexity", "monthly")
MAX_PER_ANSWER_USD = 5.0
MAX_MONTHLY_USD = 50.0
MAX_INCLUDED = 1000
SUBSCRIPTION_DAYS = 30
TIERS = ("light", "standard", "deep")


@dataclass(frozen=True)
class RunFacts:
    """What a finished run did, as recorded by the engine."""
    files: int = 0  # files handed to the helper
    tokens: int = 0  # tokens the model used
    model_calls: int = 0  # how many times the helper asked the model
    web_lookups: int = 0  # public web searches
    code_runs: int = 0  # programs run in the sealed room


def facts_from_report(rep) -> RunFacts:
    """Read the facts off a run report (its journal events), not off anything the helper says."""
    kinds = [s.get("event") for s in rep.steps]
    return RunFacts(files=len(rep.records_handed), tokens=int(rep.tokens or 0), model_calls=kinds.count("model_call"),
                    web_lookups=kinds.count("web_search"), code_runs=kinds.count("cell_run"))


def tier(f: RunFacts) -> str:
    """How demanding the run was. Deep: it ran a program, thought three or more times, or read twelve or more files.
    Standard: it thought twice, looked something up on the web, or read four or more files. Light: anything smaller."""
    if f.code_runs or f.model_calls >= 3 or f.files >= 12:
        return "deep"
    if f.model_calls >= 2 or f.web_lookups or f.files >= 4:
        return "standard"
    return "light"


def plan_of(listing) -> str:
    if listing.plan in PLANS:
        return listing.plan
    return "per_file" if listing.per_file_cents > 0 else "flat"  # listings made before plans existed


def max_cents(listing) -> int:
    p = plan_of(listing)
    if p == "complexity":
        return max(1, listing.light_cents, listing.standard_cents, listing.deep_cents)
    if p == "monthly":
        return max(1, round(listing.monthly_usd * 100))
    return max(1, round(listing.price_usd * 100))


def cents_for(listing, facts) -> int:
    """The real price of one answer. `facts` may be a RunFacts or just a number of files (older callers)."""
    f = facts if isinstance(facts, RunFacts) else RunFacts(files=int(facts))
    p, cap = plan_of(listing), max_cents(listing)
    base = round(listing.base_usd * 100)
    if p == "per_file":
        return max(1, min(cap, base + listing.per_file_cents * max(0, f.files)))
    if p == "per_token":
        return max(1, min(cap, base + math.ceil(max(0, f.tokens) * listing.per_1k_tokens_cents / 1000)))
    if p == "complexity":
        return max(1, getattr(listing, tier(f) + "_cents") or cap)
    return cap  # flat; and a monthly plan's one payment is the fee itself


def explain(listing, facts: RunFacts) -> str:
    p = plan_of(listing)
    if p == "per_file":
        return f"it read {facts.files} file{'s' if facts.files != 1 else ''}"
    if p == "per_token":
        return f"it used {facts.tokens:,} tokens"
    if p == "complexity":
        bits = [f"{facts.model_calls} thinking step{'s' if facts.model_calls != 1 else ''}"]
        if facts.web_lookups:
            bits.append(f"{facts.web_lookups} web lookup{'s' if facts.web_lookups != 1 else ''}")
        if facts.code_runs:
            bits.append("a program run")
        bits.append(f"{facts.files} file{'s' if facts.files != 1 else ''} read")
        return f"{tier(facts).capitalize()}: " + ", ".join(bits)
    return "one price"


def text(listing) -> str:
    p = plan_of(listing)
    if p == "per_file":
        return f"{max(1, round(listing.base_usd * 100))}¢ + {listing.per_file_cents}¢ per file it reads, at most {max_cents(listing)}¢"
    if p == "per_token":
        return f"{round(listing.base_usd * 100)}¢ + {listing.per_1k_tokens_cents}¢ per 1,000 tokens, at most {max_cents(listing)}¢"
    if p == "complexity":
        return f"{listing.light_cents}¢ light, {listing.standard_cents}¢ standard, {listing.deep_cents}¢ deep"
    if p == "monthly":
        return f"${listing.monthly_usd:.2f} a month, up to {listing.included_answers} answers, no automatic renewal"
    return f"{max_cents(listing)}¢ per answer"


class PricingError(ValueError):
    """The plan cannot be used; the message says why in plain words."""


def _money(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        raise PricingError(f"{what} must be between ${lo:.2f} and ${hi:.2f}")
    return round(float(v), 2)


def _cents(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise PricingError(f"{what} must be a whole number of cents between {lo} and {hi}")
    return v


def validate(body: dict) -> dict:
    """Turn what the Publish form sent into the fields of a Listing, refusing anything that does not add up."""
    plan = body.get("plan") or ("per_file" if body.get("per_file_cents") else "flat")
    if plan not in PLANS:
        raise PricingError("choose how this helper charges")
    out = {"plan": plan, "price_usd": 0.0, "base_usd": 0.0, "per_file_cents": 0, "per_1k_tokens_cents": 0,
           "light_cents": 0, "standard_cents": 0, "deep_cents": 0, "monthly_usd": 0.0, "included_answers": 0}
    if plan == "flat":
        out["price_usd"] = _money(body.get("price_usd"), 0.01, MAX_PER_ANSWER_USD, "the price per answer")
    elif plan in ("per_file", "per_token"):
        out["price_usd"] = _money(body.get("price_usd"), 0.01, MAX_PER_ANSWER_USD, "the most one answer can cost")
        out["base_usd"] = _money(body.get("base_usd", 0) or 0, 0, out["price_usd"], "the starting price")
        key, what = ("per_file_cents", "the price per file") if plan == "per_file" else ("per_1k_tokens_cents", "the price per 1,000 tokens")
        out[key] = _cents(body.get(key), 1, 500, what)
    elif plan == "complexity":
        vals = [_cents(body.get(k), 1, int(MAX_PER_ANSWER_USD * 100), f"the {k.split('_')[0]} price") for k in ("light_cents", "standard_cents", "deep_cents")]
        if not vals[0] <= vals[1] <= vals[2]:
            raise PricingError("light must not cost more than standard, and standard not more than deep")
        out.update(light_cents=vals[0], standard_cents=vals[1], deep_cents=vals[2], price_usd=round(vals[2] / 100, 2))
    else:  # monthly
        out["monthly_usd"] = _money(body.get("monthly_usd"), 0.5, MAX_MONTHLY_USD, "the monthly fee")
        inc = body.get("included_answers")
        if isinstance(inc, bool) or not isinstance(inc, int) or not 1 <= inc <= MAX_INCLUDED:
            raise PricingError(f"the number of answers included must be a whole number between 1 and {MAX_INCLUDED}")
        out["included_answers"] = inc
        out["price_usd"] = out["monthly_usd"]
    return out
