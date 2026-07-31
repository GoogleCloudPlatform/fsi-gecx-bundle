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
