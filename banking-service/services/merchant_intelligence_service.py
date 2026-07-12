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

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar


RESOURCE_PATH = Path(__file__).resolve().parents[1] / "resources" / "data" / "merchant_intelligence.json"


def _descriptor_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Z0-9]+", value.upper())


def _normalize_descriptor(value: str) -> str:
    return " ".join(_descriptor_tokens(value))


@dataclass(frozen=True)
class MerchantIntelligenceMatch:
    normalized_merchant: str
    merchant_type: str
    mccs: list[str]
    merchant_risk_score: int
    flags: list[str]
    match_type: str
    matched_alias: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": True,
            "normalized_merchant": self.normalized_merchant,
            "merchant_type": self.merchant_type,
            "mccs": list(self.mccs),
            "merchant_risk_score": self.merchant_risk_score,
            "flags": list(self.flags),
            "match_type": self.match_type,
            "matched_alias": self.matched_alias,
        }


class MerchantIntelligenceService:
    """Deterministic merchant intelligence lookup backed by a curated JSON resource."""

    _loaded: ClassVar[bool] = False
    _records: ClassVar[list[dict[str, Any]]] = []
    _alias_index: ClassVar[list[tuple[str, dict[str, Any]]]] = []

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._loaded = False
        cls._records = []
        cls._alias_index = []

    @classmethod
    def _load_if_needed(cls) -> None:
        if cls._loaded:
            return

        rows = json.loads(RESOURCE_PATH.read_text(encoding="utf-8"))
        cls._records = rows
        alias_index: list[tuple[str, dict[str, Any]]] = []
        for row in rows:
            aliases = {row["name"], *row.get("aliases", [])}
            for alias in aliases:
                normalized_alias = _normalize_descriptor(alias)
                if normalized_alias:
                    alias_index.append((normalized_alias, row))

        cls._alias_index = sorted(alias_index, key=lambda item: len(item[0]), reverse=True)
        cls._loaded = True

    @classmethod
    def lookup(cls, raw_descriptor: str, mcc: str | None = None) -> dict[str, Any]:
        cls._load_if_needed()
        normalized_descriptor = _normalize_descriptor(raw_descriptor)
        descriptor_tokens = set(normalized_descriptor.split())

        for alias, row in cls._alias_index:
            alias_tokens = set(alias.split())
            exact_match = normalized_descriptor == alias
            substring_match = alias in normalized_descriptor or normalized_descriptor in alias
            token_match = bool(alias_tokens) and alias_tokens.issubset(descriptor_tokens)
            if exact_match or substring_match or token_match:
                match = MerchantIntelligenceMatch(
                    normalized_merchant=row["name"],
                    merchant_type=row.get("type", "unknown"),
                    mccs=[str(code) for code in row.get("mccs", [])],
                    merchant_risk_score=int(row.get("risk", 0)),
                    flags=sorted(str(flag).upper() for flag in row.get("flags", [])),
                    match_type="exact" if exact_match else "alias",
                    matched_alias=alias,
                )
                result = match.to_dict()
                result["mcc_match"] = bool(mcc and str(mcc) in result["mccs"])
                return result

        return {
            "matched": False,
            "normalized_merchant": normalized_descriptor.title() if normalized_descriptor else None,
            "merchant_type": None,
            "mccs": [],
            "merchant_risk_score": None,
            "flags": [],
            "match_type": None,
            "matched_alias": None,
            "mcc_match": False,
        }
