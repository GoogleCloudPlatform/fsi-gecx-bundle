from services.knowledge_catalog import KnowledgeCatalogService


def main() -> None:
    service = KnowledgeCatalogService()
    topic_ids = service.sync_topics_to_catalog()
    print("Synced fraud support guidance topics:")
    for topic_id in topic_ids:
        print(f"- {topic_id}")


if __name__ == "__main__":
    main()
