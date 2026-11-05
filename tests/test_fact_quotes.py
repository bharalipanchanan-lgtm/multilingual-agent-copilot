"""Quote validator for the fact table (handoff task 3).

Every evidence quote in facts/*.json must be found on its stated physical page of the policy
PDF after NFKC, quote mark, case and whitespace normalisation (fact_table.norm). Each quote is
its own test case, so a failure names the policy, plan, attribute, page and quote.

  pytest tests/test_fact_quotes.py            all checks
  pytest tests/test_fact_quotes.py -rA -q     with a line per quote
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fact_table import load_facts, norm, page_texts, quote_results, schema_problems  # noqa: E402

FACTS = load_facts()
CURRENT = [f for f in FACTS if not f["legacy"]]
QUOTES = [q for f in CURRENT for q in quote_results(f)]


def _id(q):
    return f"{q['policy_id']}-{q['plan']}-{q['attribute']}-p{q['page']}-{(q['quote'] or '')[:30]}"


def test_fact_files_present():
    assert CURRENT, "no format 2 fact files in facts/"


@pytest.mark.parametrize("f", CURRENT, ids=[f["policy_id"] for f in CURRENT])
def test_schema(f):
    assert schema_problems(f) == []


@pytest.mark.parametrize("q", QUOTES, ids=[_id(q) for q in QUOTES])
def test_quote_on_its_page(q):
    assert q["quote"], "empty quote"
    elsewhere = f" (found on page {q['found_on']} instead)" if q["found_on"] else ""
    assert q["found"], f"quote not on page {q['page']}{elsewhere}: {q['quote']!r}"


def test_legacy_files_are_not_counted_as_verified():
    # Legacy files have no verbatim quotes, so they cannot pass this validator. They stay
    # listed here until task 5 rebuilds them, rather than being skipped silently.
    legacy = [f["file"] for f in FACTS if f["legacy"]]
    for f in FACTS:
        if f["legacy"]:
            assert all(e["quote"] is None for r in f["rows"] for e in r["evidence"])
    if legacy:
        pytest.xfail(f"legacy fact files without quotes, rebuilt in task 5: {legacy}")


def _probe(f, quote, page):
    probe = {"policy_id": f["policy_id"], "rows": [{"plan": "ALL", "attribute": "probe",
                                                    "evidence": [{"page": page, "quote": quote}]}]}
    return quote_results(probe)[0]


def _first_quote():
    for f in CURRENT:
        for r in f["rows"]:
            for e in r["evidence"]:
                if e["quote"] and any(ch.isdigit() for ch in e["quote"]):
                    return f, e
    pytest.skip("no quote with a digit")


def test_validator_catches_a_changed_figure():
    # guards against a normaliser so loose that a wrong number still "matches"
    f, e = _first_quote()
    i = next(i for i, ch in enumerate(e["quote"]) if ch.isdigit())
    bad = e["quote"][:i] + str((int(e["quote"][i]) + 1) % 10) + e["quote"][i + 1:]
    assert not _probe(f, bad, e["page"])["found"]


def test_validator_catches_a_wrong_page():
    f, e = _first_quote()
    texts = page_texts(f["policy_id"])
    other = next(p for p in range(1, len(texts) + 1) if p != e["page"] and norm(e["quote"]) not in texts[p - 1])
    assert not _probe(f, e["quote"], other)["found"]
