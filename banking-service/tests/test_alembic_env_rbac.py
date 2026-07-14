from pathlib import Path


def test_alembic_env_revokes_immutable_ledger_permissions_for_all_roles() -> None:
    env_text = Path(__file__).parents[1].joinpath("alembic", "env.py").read_text()

    assert "immutable_ledger_roles = set(roles + viewer_roles)" in env_text
    assert 'reset_schemas = [s for s in schemas if s not in {"admin", "voice_support_sessions"}]' in env_text
    assert 'allowed_schemas = ["voice_support_sessions"]' in env_text
    assert 'reset_sa_names = ["banking-db-reset-sa"]' in env_text
    assert "bootstrap_roles = [" in env_text
    assert 'if "@" not in role' in env_text
    assert "for role in bootstrap_roles:" in env_text
    assert "for role in reset_roles:" in env_text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES" in env_text
    assert 'elif role.startswith("banking-service-sa"):' in env_text
    assert '"ledger",' in env_text
    assert 'REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM "{role}"' in env_text
    assert 'REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM PUBLIC' in env_text
    assert 'if role.startswith("banking-service-sa"):\n                        continue' not in env_text
    assert 'if "ledger" in allowed_schemas:' not in env_text


def test_alembic_env_verifies_cdc_source_permissions() -> None:
    env_text = Path(__file__).parents[1].joinpath("alembic", "env.py").read_text()

    assert "SELECT rolreplication" in env_text
    assert "has_database_privilege(:username, current_database(), 'CONNECT')" in env_text
    assert "has_schema_privilege(:username, oid, 'USAGE')" in env_text
    assert "has_table_privilege(:username, c.oid, 'SELECT')" in env_text
    assert "CDC source permission verification failed" in env_text
    assert "if require_cdc_bootstrap:\n                        raise" in env_text
