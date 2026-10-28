# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The curated credit knowledge corpus: freshness, catalog traceability, policy hygiene."""
import re
from decimal import Decimal

import pytest

from services.credit_knowledge_corpus import (
    CORPUS_DIR,
    DOCUMENTS_FILE,
    GROUNDED_FIELDS,
    MANIFEST_FILE,
    MAX_SPAN_CHARS,
    PolicyDocument,
    build_corpus,
    generate_committed_corpus_files,
    load_corpus,
    load_policy_documents,
    render_corpus_files,
    stale_corpus_files,
)
from services.credit_product_catalog import load_credit_product_seed


def _spans(snapshot, doc_id):
    return {
        r["structData"]["section_id"]: r["structData"]["text_span"]
        for r in snapshot.records
        if r["structData"]["doc_id"] == doc_id
    }


def test_committed_corpus_matches_a_fresh_generation_byte_for_byte():
    # Fails when credit_products.json or policies.json changes without a regen.
    expected = generate_committed_corpus_files()
    for name in (MANIFEST_FILE, DOCUMENTS_FILE):
        assert (CORPUS_DIR / name).read_bytes() == expected[name].encode("utf-8"), name
    assert stale_corpus_files() == []


def test_generation_is_deterministic_and_snapshot_tracks_content():
    seeds, policies = load_credit_product_seed(), load_policy_documents()
    first = render_corpus_files(build_corpus(seeds, policies))
    assert first == render_corpus_files(build_corpus(seeds, policies))

    changed = [seeds[0].model_copy(update={"purchase_apr": Decimal("0.1111")}), *seeds[1:]]
    other = build_corpus(changed, policies)
    assert other.snapshot_id != build_corpus(seeds, policies).snapshot_id
    assert "11.11%" in _spans(other, f"CARD-{seeds[0].product_code}")["purchase-apr"]


def test_shipped_snapshot_loads_and_every_record_is_grounded_and_bounded():
    snapshot = load_corpus()
    assert snapshot.manifest["record_count"] == len(snapshot.records)
    for record in snapshot.records:
        struct = record["structData"]
        assert struct["snapshot_id"] == snapshot.snapshot_id
        assert all(struct[f] for f in GROUNDED_FIELDS)
        assert len(struct["text_span"]) <= MAX_SPAN_CHARS
        assert struct["citation"] == (
            f"{struct['short_title']} §{struct['section_id']} (snapshot {snapshot.snapshot_id})"
        )


def test_every_product_fact_traces_to_a_catalog_field():
    base = load_credit_product_seed()[0]
    distinctive = base.model_copy(update={
        "product_code": "FIXTURE_CARD",
        "product_name": "Fixture Card",
        "tagline": "Fixture tagline zq1",
        "best_for": "Fixture best-for zq2",
        "purchase_apr": Decimal("0.1234"),
        "intro_purchase_apr": Decimal("0.0111"),
        "intro_purchase_apr_months": 7,
        "intro_balance_transfer_apr": Decimal("0.0222"),
        "intro_balance_transfer_apr_months": 9,
        "balance_transfer_fee_rate": Decimal("0.0333"),
        "balance_transfer_fee_minimum_minor": 777,
        "cash_advance_apr": Decimal("0.2345"),
        "cash_advance_fee_rate": Decimal("0.0444"),
        "cash_advance_fee_minimum_minor": 6789,
        "foreign_transaction_fee_rate": Decimal("0.0155"),
        "late_fee_maximum_minor": 4321,
        "returned_payment_fee_maximum_minor": 3210,
        "penalty_apr": Decimal("0.3456"),
        "travel_multiplier": 4,
        "dining_multiplier": 6,
        "is_secured": True,
        "features": ["ZZ unique feature one", "ZZ unique feature two"],
    })
    distinctive = distinctive.model_copy(update={"annual_fee_cents": 12345, "min_credit_limit_cents": 432100, "max_credit_limit_cents": 9876500})
    spans = _spans(build_corpus([distinctive], []), "CARD-FIXTURE_CARD")

    assert spans["overview"] == "Fixture tagline zq1. Best for: Fixture best-for zq2. Secured card: yes."
    assert spans["purchase-apr"] == "Purchase APR: 12.34%. Intro purchase APR: 1.11% intro APR for 7 months."
    assert spans["balance-transfers"] == (
        "Balance transfer fee: 3.33% (minimum USD 7.77). Intro balance transfer APR: 2.22% intro APR for 9 months."
    )
    assert spans["cash-advances"] == "Cash advance APR: 23.45%. Cash advance fee: 4.44% (minimum USD 67.89)."
    assert spans["fees"] == (
        "Annual fee: USD 123.45. Foreign transaction fee: 1.55%. Late fee: up to USD 43.21. "
        "Returned payment fee: up to USD 32.10."
    )
    assert spans["penalty-apr"] == "Penalty APR: 34.56%."
    assert spans["rewards"] == "4x points on travel, 6x points on dining, 1x points on everything else."
    assert spans["credit-limits"] == "Credit limit range: USD 4,321.00 minimum to USD 98,765.00 maximum."
    assert spans["feature-1"] == "ZZ unique feature one"
    assert spans["feature-2"] == "ZZ unique feature two"
    assert len(spans) == 10


def test_absent_offers_render_as_none_and_inactive_products_are_excluded():
    seeds = load_credit_product_seed()
    plain = seeds[0].model_copy(update={
        "intro_purchase_apr": None, "intro_purchase_apr_months": None,
        "intro_balance_transfer_apr": None, "intro_balance_transfer_apr_months": None,
        "penalty_apr": None,
    })
    retired = seeds[1].model_copy(update={"is_active": False})
    snapshot = build_corpus([plain, retired], [])
    spans = _spans(snapshot, f"CARD-{plain.product_code}")
    assert spans["penalty-apr"] == "Penalty APR: none."
    assert spans["purchase-apr"].endswith("Intro purchase APR: none.")
    assert {d["doc_id"] for d in snapshot.manifest["documents"]} == {f"CARD-{plain.product_code}"}


def _policy(text, section_id="s1"):
    return PolicyDocument.model_validate({
        "doc_id": "POLICY-TEST", "title": "Test", "short_title": "Test",
        "sections": [{"section_id": section_id, "heading": "H", "text": text}],
    })


def test_section_over_budget_raises_naming_doc_and_section():
    with pytest.raises(ValueError, match=r"POLICY-TEST §too-long: text_span is 201 chars"):
        build_corpus([], [_policy("x" * 201, "too-long")])
    build_corpus([], [_policy("x" * 200)])


def test_overlong_product_record_id_is_rejected():
    seed = load_credit_product_seed()[0].model_copy(update={"product_code": "P" * 50})
    with pytest.raises(ValueError, match="not a valid document id"):
        build_corpus([seed], [])


_PER_PRODUCT_FIGURE = re.compile(r"%|\$\s*\d|\bUSD\b|\d+(\.\d+)?\s*(percent|dollars?)\b", re.IGNORECASE)


def test_no_policy_section_restates_a_per_product_figure():
    policies = load_policy_documents()
    assert {p.doc_id for p in policies} >= {
        "POLICY-APPLY", "POLICY-PAYMENTS", "POLICY-CREDIT-LIMIT", "POLICY-SECURED-GRADUATION",
        "POLICY-LOST-STOLEN-FRAUD", "POLICY-DISPUTES", "POLICY-FEES", "POLICY-CONTACT",
    }
    for policy in policies:
        for section in policy.sections:
            assert not _PER_PRODUCT_FIGURE.search(section.text), f"{policy.doc_id} §{section.section_id}"


def test_policy_figure_check_catches_rates_and_amounts():
    for text in ("The late fee is USD 40.00.", "Purchase APR is 22.49%.", "Pay $40 late.", "about 5 percent"):
        assert _PER_PRODUCT_FIGURE.search(text), text
