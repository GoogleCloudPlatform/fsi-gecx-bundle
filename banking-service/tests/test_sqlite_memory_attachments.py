from utils.database import create_db_engine


def test_shared_memory_schema_attachments_do_not_create_literal_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    engine = create_db_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    engine.dispose()

    assert list(tmp_path.glob("file:*mode=memory*cache=shared*")) == []
