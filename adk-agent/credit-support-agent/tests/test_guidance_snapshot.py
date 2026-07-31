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

from agent.guidance_snapshot import guidance_observability_payload


def test_guidance_observability_payload_excludes_prompt_and_topic_content() -> None:
    payload = guidance_observability_payload(
        {
            "schema_version": 1,
            "snapshot_id": "snapshot-1",
            "source": "knowledge_catalog",
            "topic_ids": ["fraud_golden_path"],
            "content_version": "2.0",
            "retrieved_at": "2026-07-14T12:00:00Z",
            "fallback_reason": None,
            "freshness": {
                "status": "FRESH",
                "oldest_last_reviewed": "2026-07-09",
            },
            "topics": [{"must_do": ["internal guidance"]}],
            "agent_guidance_summary": "private prompt material",
        }
    )

    assert payload["source"] == "knowledge_catalog"
    assert payload["freshness_status"] == "FRESH"
    assert "topics" not in payload
    assert "agent_guidance_summary" not in payload
