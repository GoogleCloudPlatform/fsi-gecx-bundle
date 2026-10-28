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

"""Curated credit knowledge corpus: one owner for its content, ids and snapshot.

Guarantees:
- Product documents are rendered only from ``credit_products.json`` through
  ``present_credit_product``; every figure is a presentation ``display_text``.
  Policy documents are hand-authored in ``policies.json`` and carry no
  per-product figures (they point to the product terms instead).
- Every section is one search record whose ``text_span`` is at most
  ``MAX_SPAN_CHARS``; the builder raises instead of truncating, so a snippet is
  always a whole stored section.
- ``snapshot_id`` is derived from record content only, and the rendered files
  are byte-for-byte deterministic. The committed snapshot under
  ``resources/knowledge/credit/corpus`` is what the banking-service image ships,
  what the import job loads into the data store, and what search results are
  grounded against.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from models.credit_card import CreditProduct
from models.credit_product_catalog import CreditProductResponse, CreditProductSeed
from services.credit_product_catalog import load_credit_product_seed, present_credit_product

CORPUS_SCHEMA_VERSION = 1
MAX_SPAN_CHARS = 200
KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "resources" / "knowledge" / "credit"
POLICIES_PATH = KNOWLEDGE_DIR / "policies.json"
CORPUS_DIR = KNOWLEDGE_DIR / "corpus"
MANIFEST_FILE = "manifest.json"
DOCUMENTS_FILE = "documents.jsonl"
GENERATOR = "banking-service/scripts/generate_credit_knowledge_corpus.py"

GROUNDED_FIELDS = ("doc_id", "section_id", "short_title", "snapshot_id", "text_span")
"""structData fields every search result must return and match the stored section."""
SEARCHABLE_FIELDS = ("title", "short_title", "heading", "text_span")
INDEXABLE_FIELDS = ("snapshot_id", "doc_id", "section_id", "kind", "product_code")
STRUCT_FIELDS = tuple(
    sorted(set(GROUNDED_FIELDS) | set(SEARCHABLE_FIELDS) | set(INDEXABLE_FIELDS) | {"citation"})
)

_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")
_SECTION_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")


class PolicySection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_id: str = Field(pattern=_SECTION_ID.pattern)
    heading: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1)


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str = Field(pattern=r"^POLICY-[A-Z0-9-]{1,40}$")
    title: str = Field(min_length=1, max_length=120)
    short_title: str = Field(min_length=1, max_length=80)
    sections: list[PolicySection] = Field(min_length=1)


@dataclass(frozen=True)
class CorpusSnapshot:
    manifest: dict[str, Any]
    records: tuple[dict[str, Any], ...]

    @property
    def snapshot_id(self) -> str:
        return str(self.manifest["snapshot_id"])

    def records_by_id(self) -> dict[str, dict[str, Any]]:
        return {record["id"]: record for record in self.records}


@dataclass(frozen=True)
class _Section:
    section_id: str
    heading: str
    text: str


@dataclass(frozen=True)
class _Document:
    doc_id: str
    kind: str
    title: str
    short_title: str
    product_code: str | None
    sections: tuple[_Section, ...]


def format_citation(short_title: str, section_id: str, snapshot_id: str) -> str:
    return f"{short_title} §{section_id} (snapshot {snapshot_id})"


def load_policy_documents(path: Path = POLICIES_PATH) -> list[PolicyDocument]:
    with path.open("r", encoding="utf-8") as handle:
        documents = [PolicyDocument.model_validate(item) for item in json.load(handle)]
    ids = [document.doc_id for document in documents]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate policy doc_id in knowledge policies.")
    return documents


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _product_sections(product: CreditProductResponse) -> list[_Section]:
    intro_purchase = product.intro_purchase_apr
    intro_transfer = product.intro_balance_transfer_apr
    penalty = product.penalty_apr
    sections = [
        _Section(
            "overview",
            "Overview",
            f"{_sentence(product.tagline)} Best for: {_sentence(product.best_for)} "
            f"Secured card: {'yes' if product.is_secured else 'no'}.",
        ),
        _Section(
            "purchase-apr",
            "Purchase APR",
            f"Purchase APR: {product.purchase_apr.display_text}. Intro purchase APR: "
            f"{intro_purchase.display_text if intro_purchase else 'none'}.",
        ),
        _Section(
            "balance-transfers",
            "Balance transfers",
            f"Balance transfer fee: {product.balance_transfer_fee_rate.display_text} "
            f"(minimum {product.balance_transfer_fee_minimum.display_text}). "
            f"Intro balance transfer APR: {intro_transfer.display_text if intro_transfer else 'none'}.",
        ),
        _Section(
            "cash-advances",
            "Cash advances",
            f"Cash advance APR: {product.cash_advance_apr.display_text}. "
            f"Cash advance fee: {product.cash_advance_fee_rate.display_text} "
            f"(minimum {product.cash_advance_fee_minimum.display_text}).",
        ),
        _Section(
            "fees",
            "Fees",
            f"Annual fee: {product.annual_fee.display_text}. "
            f"Foreign transaction fee: {product.foreign_transaction_fee_rate.display_text}. "
            f"Late fee: up to {product.late_fee_maximum.display_text}. "
            f"Returned payment fee: up to {product.returned_payment_fee_maximum.display_text}.",
        ),
        _Section(
            "penalty-apr",
            "Penalty APR",
            f"Penalty APR: {penalty.display_text if penalty else 'none'}.",
        ),
        _Section("rewards", "Rewards", _sentence(product.rewards.display_text)),
        _Section(
            "credit-limits",
            "Credit limits",
            f"Credit limit range: {product.min_credit_limit.display_text} minimum to "
            f"{product.max_credit_limit.display_text} maximum.",
        ),
    ]
    sections += [
        _Section(f"feature-{index}", "Feature", feature)
        for index, feature in enumerate(product.features, start=1)
    ]
    return sections


def _product_document(seed: CreditProductSeed) -> _Document:
    # A transient ORM row: the catalog's single presentation path renders every figure.
    product = present_credit_product(CreditProduct(**seed.model_dump()))
    return _Document(
        doc_id=f"CARD-{product.product_code}",
        kind="PRODUCT",
        title=f"{product.product_name} card terms",
        short_title=product.product_name,
        product_code=product.product_code,
        sections=tuple(_product_sections(product)),
    )


def _policy_document(policy: PolicyDocument) -> _Document:
    return _Document(
        doc_id=policy.doc_id,
        kind="POLICY",
        title=policy.title,
        short_title=policy.short_title,
        product_code=None,
        sections=tuple(_Section(s.section_id, s.heading, s.text) for s in policy.sections),
    )


def _unstamped_records(documents: list[_Document]) -> list[dict[str, Any]]:
    records = []
    for document in documents:
        section_ids = [section.section_id for section in document.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError(f"{document.doc_id}: duplicate section_id")
        for section in document.sections:
            where = f"{document.doc_id} §{section.section_id}"
            if not _SECTION_ID.match(section.section_id):
                raise ValueError(f"{where}: invalid section_id")
            if len(section.text) > MAX_SPAN_CHARS:
                raise ValueError(
                    f"{where}: text_span is {len(section.text)} chars; the limit is {MAX_SPAN_CHARS}"
                )
            record_id = f"{document.doc_id}-{section.section_id}"
            if not _RECORD_ID.match(record_id):
                raise ValueError(f"{where}: record id {record_id!r} is not a valid document id")
            struct = {
                "doc_id": document.doc_id,
                "kind": document.kind,
                "title": document.title,
                "short_title": document.short_title,
                "section_id": section.section_id,
                "heading": section.heading,
                "text_span": section.text,
            }
            if document.product_code is not None:
                struct["product_code"] = document.product_code
            records.append({"id": record_id, "structData": struct})
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate knowledge record ids.")
    return records


def compute_snapshot_id(unstamped_records: list[dict[str, Any]]) -> str:
    canonical = json.dumps(unstamped_records, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return f"{CORPUS_SCHEMA_VERSION}-{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"


def build_corpus(
    seeds: list[CreditProductSeed], policies: list[PolicyDocument]
) -> CorpusSnapshot:
    active = sorted(
        (seed for seed in seeds if seed.is_active),
        key=lambda seed: (seed.display_order, seed.product_code),
    )
    documents = [_product_document(seed) for seed in active]
    documents += [_policy_document(policy) for policy in policies]
    records = _unstamped_records(documents)
    snapshot_id = compute_snapshot_id(records)
    for record in records:
        struct = record["structData"]
        struct["snapshot_id"] = snapshot_id
        struct["citation"] = format_citation(struct["short_title"], struct["section_id"], snapshot_id)
    manifest = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "generator": GENERATOR,
        "record_count": len(records),
        "documents": [
            {
                "doc_id": document.doc_id,
                "kind": document.kind,
                "title": document.title,
                "short_title": document.short_title,
                "sections": [section.section_id for section in document.sections],
            }
            for document in documents
        ],
    }
    return CorpusSnapshot(manifest=manifest, records=tuple(records))


def render_corpus_files(snapshot: CorpusSnapshot) -> dict[str, str]:
    manifest = json.dumps(snapshot.manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    documents = "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n"
        for record in snapshot.records
    )
    return {MANIFEST_FILE: manifest, DOCUMENTS_FILE: documents}


def generate_committed_corpus_files() -> dict[str, str]:
    """The corpus files the committed catalog and policies must reproduce."""
    return render_corpus_files(build_corpus(load_credit_product_seed(), load_policy_documents()))


def stale_corpus_files(corpus_dir: Path = CORPUS_DIR) -> list[str]:
    """Names of corpus files that differ from a fresh generation (empty when fresh)."""
    expected = generate_committed_corpus_files()
    stale = []
    for name, text in expected.items():
        path = corpus_dir / name
        if not path.is_file() or path.read_bytes() != text.encode("utf-8"):
            stale.append(name)
    return stale


def write_corpus_files(files: dict[str, str], corpus_dir: Path = CORPUS_DIR) -> None:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (corpus_dir / name).write_bytes(text.encode("utf-8"))


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> CorpusSnapshot:
    """Load the shipped snapshot; raises if it is missing or internally inconsistent."""
    manifest = json.loads((corpus_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != CORPUS_SCHEMA_VERSION:
        raise ValueError("Unsupported credit knowledge corpus schema_version.")
    snapshot_id = str(manifest.get("snapshot_id") or "")
    lines = (corpus_dir / DOCUMENTS_FILE).read_text(encoding="utf-8").splitlines()
    records = tuple(json.loads(line) for line in lines if line.strip())
    if not snapshot_id or len(records) != manifest.get("record_count"):
        raise ValueError("Credit knowledge corpus manifest does not match its documents.")
    for record in records:
        struct = record.get("structData") or {}
        if struct.get("snapshot_id") != snapshot_id or any(
            not str(struct.get(field) or "").strip() for field in GROUNDED_FIELDS
        ):
            raise ValueError(f"Credit knowledge record {record.get('id')!r} is not grounded in the snapshot.")
    return CorpusSnapshot(manifest=manifest, records=records)
