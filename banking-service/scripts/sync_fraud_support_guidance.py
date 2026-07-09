import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.knowledge_catalog import KnowledgeCatalogService


def main() -> None:
    service = KnowledgeCatalogService()
    topic_ids = service.sync_topics_to_catalog()
    print("Synced fraud support guidance topics:")
    for topic_id in topic_ids:
        print(f"- {topic_id}")


if __name__ == "__main__":
    main()
