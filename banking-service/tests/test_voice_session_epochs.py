from services.voice_session_epochs import (
    bump_customer_reset_generation,
    bump_global_reset_generation,
    get_reset_generation,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_sqlite_uses_stable_local_reset_generation():
    with Session(create_engine("sqlite:///:memory:")) as db_session:
        assert get_reset_generation(db_session, "presenter-1") == {
            "global_epoch": 0,
            "customer_epoch": 0,
            "token": "0:0",
        }


class _PostgresSession:
    class _Bind:
        class _Dialect:
            name = "postgresql"

        dialect = _Dialect()

    class _Result:
        def all(self):
            return [("GLOBAL", 3), ("CUSTOMER", 9)]

    def __init__(self):
        self.statements = []
        self.commits = 0

    def get_bind(self):
        return self._Bind()

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        return self._Result()

    def commit(self):
        self.commits += 1


def test_postgres_generation_combines_global_and_customer_epochs():
    db = _PostgresSession()
    assert get_reset_generation(db, "presenter-1")["token"] == "3:9"
    assert db.statements[0][1] == {"customer_id": "presenter-1"}


def test_reset_generation_bumps_are_committed():
    db = _PostgresSession()
    bump_customer_reset_generation(db, "presenter-1")
    bump_global_reset_generation(db)
    assert db.commits == 2
    assert "scope_type, scope_id" in db.statements[0][0]
    assert db.statements[0][1] == {"customer_id": "presenter-1"}
    assert "'GLOBAL', '*'" in db.statements[1][0]
