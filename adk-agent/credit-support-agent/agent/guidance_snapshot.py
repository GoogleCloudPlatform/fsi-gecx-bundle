"""Safe observability projection for governed support-guidance snapshots."""

from __future__ import annotations


SAFE_GUIDANCE_FIELDS = (
    "schema_version",
    "snapshot_id",
    "source",
    "topic_ids",
    "content_version",
    "retrieved_at",
    "fallback_reason",
)


def guidance_observability_payload(snapshot: dict | None) -> dict:
    snapshot = snapshot or {}
    payload = {field: snapshot.get(field) for field in SAFE_GUIDANCE_FIELDS}
    freshness = snapshot.get("freshness") or {}
    payload["freshness_status"] = freshness.get("status")
    payload["oldest_last_reviewed"] = freshness.get("oldest_last_reviewed")
    return payload
