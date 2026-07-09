from pathlib import Path


def test_alembic_env_revokes_immutable_ledger_permissions_for_all_roles() -> None:
    env_text = Path(__file__).parents[1].joinpath("alembic", "env.py").read_text()

    assert "immutable_ledger_roles = set(roles + viewer_roles)" in env_text
    assert 'REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM "{role}"' in env_text
    assert 'REVOKE UPDATE, DELETE ON TABLE ledger.account_ledger FROM PUBLIC' in env_text
    assert 'if "ledger" in allowed_schemas:' not in env_text
