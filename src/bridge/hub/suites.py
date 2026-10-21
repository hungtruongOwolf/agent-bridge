"""Certifier suites as data.

A suite is a YAML file: sets of records, tasks (the question, optional earlier chat turns, and a check written as plain
conditions), and a trap vault. Adding a new kind of helper to the marketplace means adding a file, not writing code.
Files are validated when loaded, so a typo fails loudly instead of quietly scoring everyone zero.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..memory.vault import Record
from .certifier import Suite, Task

SUITE_DIR = Path(__file__).parent / "suites"
CONDITIONS = {"risk_in", "contains_all", "contains_any", "contains_n", "empty"}


class SuiteError(ValueError):
    pass


def answer_words(result: dict) -> str:
    """Everything the helper said, lower-cased: the summary and every other field except the risk label."""
    parts: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif v is not None:
            parts.append(str(v))
    walk({k: v for k, v in result.items() if k != "risk"})
    return " ".join(parts).lower()


def make_check(spec: dict, where: str):
    if not isinstance(spec, dict) or not spec:
        raise SuiteError(f"{where}: a check needs at least one condition")
    unknown = set(spec) - CONDITIONS
    if unknown:
        raise SuiteError(f"{where}: unknown condition {sorted(unknown)}; use {sorted(CONDITIONS)}")
    risk_in = spec.get("risk_in")
    all_of = [str(w).lower() for w in spec.get("contains_all", [])]
    any_of = [str(w).lower() for w in spec.get("contains_any", [])]
    n = spec.get("contains_n")
    empty = list(spec.get("empty", []))
    if n is not None and not (isinstance(n, dict) and n.get("terms") and isinstance(n.get("at_least"), int)):
        raise SuiteError(f"{where}: contains_n needs terms and at_least")

    def check(result: dict) -> bool:
        if not isinstance(result, dict):
            return False
        if any(result.get(f) not in (None, "", [], {}) for f in empty):
            return False
        text = answer_words(result)
        if risk_in is not None and result.get("risk") not in risk_in:
            return False
        if not all(w in text for w in all_of):
            return False
        if any_of and not any(w in text for w in any_of):
            return False
        if n is not None and sum(str(t).lower() in text for t in n["terms"]) < n["at_least"]:
            return False
        return True
    return check


def parse_suite(text: str) -> Suite:
    d = yaml.safe_load(text)
    if not isinstance(d, dict):
        raise SuiteError("a suite file must be a mapping")
    for k in ("id", "version", "lens_types", "record_sets", "tasks", "trap"):
        if k not in d:
            raise SuiteError(f"missing {k!r}")
    sets = {}
    for name, rows in d["record_sets"].items():
        try:
            sets[name] = tuple(Record(r["id"], r["type"], r["sensitivity"], r["text"]) for r in rows)
        except (KeyError, ValueError, TypeError) as e:
            raise SuiteError(f"record set {name!r}: {e}") from e

    def records(names, where):
        out = []
        for nm in names:
            if nm not in sets:
                raise SuiteError(f"{where}: unknown record set {nm!r}")
            out += list(sets[nm])
        ids = [r.id for r in out]
        if len(ids) != len(set(ids)):
            raise SuiteError(f"{where}: record ids must be unique across the sets it uses")
        return tuple(out)

    lens = frozenset(d["lens_types"])
    tasks = []
    for t in d["tasks"]:
        where = f"task {t.get('name')!r}"
        for k in ("name", "records", "ask", "check"):
            if k not in t:
                raise SuiteError(f"{where}: missing {k!r}")
        tasks.append(Task(t["name"], records(t["records"], where), lens, make_check(t["check"], where), t.get("goal", ""),
                          t["ask"], tuple({"role": h["role"], "text": h["text"]} for h in t.get("history", []))))
    if len({t.name for t in tasks}) != len(tasks):
        raise SuiteError("task names must be unique")
    trap = Task("trap", records(d["trap"]["records"], "trap"), lens, lambda r: True)
    return Suite(str(d["id"]), str(d["version"]), tuple(tasks), trap)


def load_suite(name: str, directory: Path = SUITE_DIR) -> Suite:
    return parse_suite((Path(directory) / f"{name}.yaml").read_text(encoding="utf-8"))


def available(directory: Path = SUITE_DIR) -> list[str]:
    return sorted(p.stem for p in Path(directory).glob("*.yaml"))
