import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TOPIC_IDS = [
    "fraud_golden_path",
    "recognized_activity",
    "replacement_card",
    "wallet_provisioning",
    "human_escalation",
]

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources" / "data"
LOCAL_GUIDANCE_FILE = RESOURCES_DIR / "fraud_support_guidance.json"


@lru_cache(maxsize=1)
def _load_local_guidance_topics() -> dict[str, dict[str, Any]]:
    with LOCAL_GUIDANCE_FILE.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {topic["topic_id"]: topic for topic in payload.get("topics", [])}


class KnowledgeCatalogService:
    def __init__(self) -> None:
        self.enabled = os.getenv("KNOWLEDGE_CATALOG_ENABLED", "false").lower() == "true"
        self.project_id = os.getenv("KNOWLEDGE_CATALOG_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("KNOWLEDGE_CATALOG_LOCATION", "us-central1")
        self.entry_group_id = os.getenv("KNOWLEDGE_CATALOG_ENTRY_GROUP_ID", "fraud-support-guidance")
        self.entry_type_id = os.getenv("KNOWLEDGE_CATALOG_ENTRY_TYPE_ID", "fraud-support-topic")
        self.policy_aspect_type_id = os.getenv("KNOWLEDGE_CATALOG_POLICY_ASPECT_TYPE_ID", "fraud-support-policy")
        self.summary_aspect_type_id = os.getenv("KNOWLEDGE_CATALOG_SUMMARY_ASPECT_TYPE_ID", "fraud-customer-summary")

    def get_guidance_bundle_for_voice_fraud(self) -> dict[str, Any]:
        return self.get_guidance_bundle(DEFAULT_TOPIC_IDS, audience="CREDIT_SUPPORT_AGENT", channel="VOICE")

    def get_guidance_bundle(
        self,
        topic_ids: list[str],
        *,
        audience: str | None = None,
        channel: str | None = None,
    ) -> dict[str, Any]:
        local_topics = self._get_local_topics(topic_ids, audience=audience, channel=channel)
        if not self.enabled:
            return self._build_bundle(topic_ids, local_topics, source="local_file")

        try:
            remote_topics = self._get_remote_topics(topic_ids, audience=audience, channel=channel)
        except Exception as exc:  # pragma: no cover - graceful runtime fallback
            logger.warning("Knowledge Catalog read failed; falling back to local guidance: %s", exc)
            return self._build_bundle(topic_ids, local_topics, source="local_file_fallback")

        merged_topics = []
        remote_by_id = {topic["topic_id"]: topic for topic in remote_topics}
        for topic_id in topic_ids:
            merged_topics.append(remote_by_id.get(topic_id) or local_topics.get(topic_id))
        merged_topics = [topic for topic in merged_topics if topic]

        source = "knowledge_catalog" if len(remote_by_id) == len(merged_topics) else "knowledge_catalog_with_local_fallback"
        return self._build_bundle(topic_ids, merged_topics, source=source)

    def sync_topics_to_catalog(self, topic_ids: list[str] | None = None) -> list[str]:
        topic_ids = topic_ids or DEFAULT_TOPIC_IDS
        topics = [topic for topic in self._get_local_topics(topic_ids).values()]
        if not self.enabled:
            raise RuntimeError("Knowledge Catalog sync requires KNOWLEDGE_CATALOG_ENABLED=true.")
        client, dataplex_v1, field_mask_pb2, struct_pb2, exceptions = self._load_dataplex_modules()
        synced_ids: list[str] = []
        entry_group_name = self._entry_group_name()

        for topic in topics:
            entry_name = self._entry_name(topic["topic_id"])
            aspects = self._build_topic_aspects(topic, dataplex_v1, struct_pb2)
            try:
                client.get_entry(
                    request=dataplex_v1.GetEntryRequest(
                        name=entry_name,
                        view=dataplex_v1.EntryView.FULL,
                    )
                )
                entry = dataplex_v1.Entry(
                    name=entry_name,
                    entry_source=dataplex_v1.EntrySource(description=topic["title"]),
                    aspects=aspects,
                )
                client.update_entry(
                    entry=entry,
                    update_mask=field_mask_pb2.FieldMask(paths=["entry_source.description", "aspects"]),
                )
            except exceptions.NotFound:
                entry = dataplex_v1.Entry(
                    entry_type=self._entry_type_name(),
                    entry_source=dataplex_v1.EntrySource(description=topic["title"]),
                    aspects=aspects,
                )
                client.create_entry(parent=entry_group_name, entry=entry, entry_id=topic["topic_id"])
            synced_ids.append(topic["topic_id"])

        return synced_ids

    def _get_local_topics(
        self,
        topic_ids: list[str],
        *,
        audience: str | None = None,
        channel: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        catalog = _load_local_guidance_topics()
        topics: dict[str, dict[str, Any]] = {}
        for topic_id in topic_ids:
            topic = catalog.get(topic_id)
            if not topic:
                continue
            if audience and topic.get("audience") != audience:
                continue
            if channel and topic.get("channel") != channel:
                continue
            topics[topic_id] = topic
        return topics

    def _get_remote_topics(
        self,
        topic_ids: list[str],
        *,
        audience: str | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        client, dataplex_v1, _field_mask_pb2, _struct_pb2, exceptions = self._load_dataplex_modules()
        topics: list[dict[str, Any]] = []
        for topic_id in topic_ids:
            try:
                entry = client.get_entry(
                    request=dataplex_v1.GetEntryRequest(
                        name=self._entry_name(topic_id),
                        view=dataplex_v1.EntryView.FULL,
                    )
                )
            except exceptions.NotFound:
                continue
            topic = self._parse_entry(entry)
            if not topic:
                continue
            if audience and topic.get("audience") != audience:
                continue
            if channel and topic.get("channel") != channel:
                continue
            topics.append(topic)
        return topics

    def _parse_entry(self, entry: Any) -> dict[str, Any] | None:
        from google.protobuf.json_format import MessageToDict

        policy_data: dict[str, Any] | None = None
        summary_data: dict[str, Any] | None = None
        for aspect in entry.aspects.values():
            aspect_type = getattr(aspect, "aspect_type", "")
            if aspect_type.endswith(f"/aspectTypes/{self.policy_aspect_type_id}"):
                policy_data = MessageToDict(aspect.data, preserving_proto_field_name=True)
            elif aspect_type.endswith(f"/aspectTypes/{self.summary_aspect_type_id}"):
                summary_data = MessageToDict(aspect.data, preserving_proto_field_name=True)

        if not policy_data:
            return None

        topic = dict(policy_data)
        if summary_data and summary_data.get("customer_safe_summary"):
            topic["customer_safe_summary"] = summary_data["customer_safe_summary"]
        return topic

    def _build_bundle(self, topic_ids: list[str], topics: list[dict[str, Any]] | dict[str, dict[str, Any]], *, source: str) -> dict[str, Any]:
        if isinstance(topics, dict):
            ordered_topics = [topics[topic_id] for topic_id in topic_ids if topic_id in topics]
        else:
            by_id = {topic["topic_id"]: topic for topic in topics}
            ordered_topics = [by_id[topic_id] for topic_id in topic_ids if topic_id in by_id]
        return {
            "source": source,
            "topic_ids": [topic["topic_id"] for topic in ordered_topics],
            "topics": ordered_topics,
            "agent_guidance_summary": self._build_agent_guidance_summary(ordered_topics),
        }

    @staticmethod
    def _build_agent_guidance_summary(topics: list[dict[str, Any]]) -> str:
        if not topics:
            return ""
        lines: list[str] = []
        for topic in topics:
            lines.append(f"- {topic['title']}:")
            for item in topic.get("must_do", []):
                lines.append(f"  - Must do: {item}")
            for item in topic.get("must_not_do", []):
                lines.append(f"  - Must not do: {item}")
            tools = topic.get("tool_dependencies", [])
            if tools:
                lines.append(f"  - Tools: {', '.join(tools)}")
        return "\n".join(lines)

    def _entry_group_name(self) -> str:
        return f"projects/{self.project_id}/locations/{self.location}/entryGroups/{self.entry_group_id}"

    def _entry_name(self, topic_id: str) -> str:
        return f"{self._entry_group_name()}/entries/{topic_id}"

    def _entry_type_name(self) -> str:
        return f"projects/{self.project_id}/locations/{self.location}/entryTypes/{self.entry_type_id}"

    def _aspect_type_name(self, aspect_type_id: str) -> str:
        return f"projects/{self.project_id}/locations/{self.location}/aspectTypes/{aspect_type_id}"

    def _aspect_key(self, aspect_type_id: str) -> str:
        return f"{self.project_id}.{self.location}.{aspect_type_id}"

    def _build_topic_aspects(self, topic: dict[str, Any], dataplex_v1: Any, struct_pb2: Any) -> dict[str, Any]:
        policy_payload = {
            "topic_id": topic["topic_id"],
            "title": topic["title"],
            "audience": topic["audience"],
            "channel": topic["channel"],
            "applies_when": topic.get("applies_when", []),
            "must_do": topic.get("must_do", []),
            "must_not_do": topic.get("must_not_do", []),
            "tool_dependencies": topic.get("tool_dependencies", []),
            "source_policy_ref": topic.get("source_policy_ref"),
            "version": topic.get("version"),
            "last_reviewed": topic.get("last_reviewed"),
        }
        summary_payload = {
            "customer_safe_summary": topic.get("customer_safe_summary", ""),
        }
        return {
            self._aspect_key(self.policy_aspect_type_id): dataplex_v1.Aspect(
                aspect_type=self._aspect_type_name(self.policy_aspect_type_id),
                data=self._dict_to_struct(policy_payload, struct_pb2),
            ),
            self._aspect_key(self.summary_aspect_type_id): dataplex_v1.Aspect(
                aspect_type=self._aspect_type_name(self.summary_aspect_type_id),
                data=self._dict_to_struct(summary_payload, struct_pb2),
            ),
        }

    @staticmethod
    def _dict_to_struct(payload: dict[str, Any], struct_pb2: Any) -> Any:
        struct = struct_pb2.Struct()
        struct.update(payload)
        return struct

    @staticmethod
    def _load_dataplex_modules():
        from google.api_core import exceptions
        from google.cloud import dataplex_v1
        from google.protobuf import field_mask_pb2, struct_pb2

        client = dataplex_v1.CatalogServiceClient()
        return client, dataplex_v1, field_mask_pb2, struct_pb2, exceptions
