"""Trusted runtime context for action-proposal adapters.

These values come from authenticated transport headers established by a runtime
adapter. They are intentionally absent from model-visible tool arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class RuntimeContextError(ValueError):
    """Trusted runtime proposal context is missing or malformed."""


def _required(headers: Mapping[str, str], name: str, *, max_length: int = 255) -> str:
    value = str(headers.get(name) or "").strip()
    if not value:
        raise RuntimeContextError(f"Missing trusted runtime header: {name}.")
    if len(value) > max_length or any(character in value for character in "\r\n"):
        raise RuntimeContextError(f"Invalid trusted runtime header: {name}.")
    return value


@dataclass(frozen=True)
class ProposalRuntimeContext:
    support_session_id: str
    runtime_name: str
    runtime_session_id: str
    customer_turn_id: str
    reset_generation: str
    catalog_snapshot_id: str | None = None
    presentation_turn_id: str | None = None
    confirmation_turn_id: str | None = None
    confirmation_method: str | None = None
    confirmation_classification: str | None = None

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> "ProposalRuntimeContext":
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        catalog_snapshot_id = (
            normalized.get("x-catalog-snapshot-id", "").strip() or None
        )
        context = cls(
            support_session_id=_required(normalized, "x-support-session-id"),
            runtime_name=_required(normalized, "x-runtime-name", max_length=64),
            runtime_session_id=_required(normalized, "x-runtime-session-id"),
            customer_turn_id=_required(normalized, "x-customer-turn-id"),
            reset_generation=_required(normalized, "x-reset-generation", max_length=64),
            catalog_snapshot_id=catalog_snapshot_id,
            presentation_turn_id=(
                normalized.get("x-proposal-presentation-turn-id", "").strip() or None
            ),
            confirmation_turn_id=(
                normalized.get("x-proposal-confirmation-turn-id", "").strip() or None
            ),
            confirmation_method=(
                normalized.get("x-proposal-confirmation-method", "").strip() or None
            ),
            confirmation_classification=(
                normalized.get("x-proposal-confirmation-classification", "").strip()
                or None
            ),
        )
        return context

    def require_customer_turn(self) -> None:
        if self.customer_turn_id == "unknown-turn":
            raise RuntimeContextError(
                "A real customer turn id is required for proposal operations."
            )

    def require_confirmation(self) -> None:
        self.require_customer_turn()
        if not self.presentation_turn_id or not self.confirmation_turn_id:
            raise RuntimeContextError(
                "Protected presentation and confirmation turn evidence is required."
            )
        if self.confirmation_turn_id == self.presentation_turn_id:
            raise RuntimeContextError(
                "Confirmation must come from a later customer turn."
            )
        if self.customer_turn_id != self.confirmation_turn_id:
            raise RuntimeContextError(
                "Current customer turn does not match the protected confirmation turn."
            )
        if self.confirmation_method != "EXPLICIT_VERBAL":
            raise RuntimeContextError("Explicit verbal confirmation is required.")
        if self.confirmation_classification != "CONFIRMED":
            raise RuntimeContextError("The protected confirmation is not affirmative.")
