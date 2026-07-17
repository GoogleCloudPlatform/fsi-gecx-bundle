import importlib.util
from pathlib import Path

from models.synthetic_schedule import SyntheticScheduledEventSchema


def _load_data_generator_schedule_model():
    module_path = (
        Path(__file__).parents[2] / "data-generator" / "scheduler" / "database.py"
    )
    spec = importlib.util.spec_from_file_location(
        "data_generator_scheduler_database_contract", module_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SyntheticScheduledEvent


def _column_contract(table) -> dict[str, tuple[str, bool]]:
    return {
        column.name: (str(column.type), column.nullable) for column in table.columns
    }


def _index_contract(table) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (index.name, tuple(column.name for column in index.columns), index.unique)
        for index in table.indexes
    }


def _unique_contract(table) -> set[tuple[str | None, tuple[str, ...]]]:
    return {
        (constraint.name, tuple(column.name for column in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }


def test_data_generator_runtime_mapping_matches_alembic_schema_contract() -> None:
    runtime_model = _load_data_generator_schedule_model()
    schema_table = SyntheticScheduledEventSchema.__table__
    runtime_table = runtime_model.__table__

    assert schema_table.schema == runtime_table.schema == "operations"
    assert _column_contract(schema_table) == _column_contract(runtime_table)
    assert _index_contract(schema_table) == _index_contract(runtime_table)
    assert _unique_contract(schema_table) == _unique_contract(runtime_table)


def test_alloydb_migration_chain_and_baseline_have_no_deployment_side_effects() -> None:
    versions = sorted(
        Path(__file__).parents[1].joinpath("alembic", "versions").glob("*.py")
    )

    assert [path.name for path in versions] == [
        "2ea57c78ba89_alloydb_unified_baseline.py",
        "7c4f2a9d1e63_canonical_journal_and_outbox_relay.py",
    ]
    baseline = versions[0].read_text()
    assert "down_revision: Union[str, Sequence[str], None] = None" in baseline
    for forbidden in (
        "cloudsql",
        "cloudsqlsuperuser",
        "CREATE ROLE",
        "GRANT ",
        "CREATE PUBLICATION",
        "pg_create_logical_replication_slot",
    ):
        assert forbidden not in baseline

    journal_migration = versions[1].read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "2ea57c78ba89"' in journal_migration
    assert "ck_account_ledger_positive_amount" in journal_migration
    assert "outbox_relay_checkpoint" in journal_migration
