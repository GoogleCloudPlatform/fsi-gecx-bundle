from pathlib import Path


def test_alembic_env_revokes_immutable_ledger_permissions_for_all_roles() -> None:
    env_text = Path(__file__).parents[1].joinpath("alembic", "env.py").read_text()

    assert "immutable_ledger_roles = set(roles + viewer_roles)" in env_text
    assert 'reset_schemas = [s for s in schemas if s != "admin"]' in env_text
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
