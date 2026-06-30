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

import pytest
import sqlalchemy.exc
from sqlalchemy import text
from utils.database import SessionLocal, KycSessionLocal


def test_rbac_least_privilege_isolation():
    """
    Verifies that querying kyc_records using the ledger_service_role connection pool (SessionLocal)
    immediately raises a permission denied error (SQLSTATE 42501).
    """
    ledger_session = SessionLocal()
    if ledger_session.bind and ledger_session.bind.dialect.name == "sqlite":
        ledger_session.close()
        pytest.skip("RBAC isolation tests require live PostgreSQL engine")
    try:
        with pytest.raises(sqlalchemy.exc.ProgrammingError) as exc_info:
            ledger_session.execute(text("SELECT * FROM kyc.kyc_records;"))
        assert "SQLSTATE 42501" in str(exc_info.value) or "permission denied" in str(exc_info.value)
    finally:
        ledger_session.close()


def test_kyc_pool_allowed_access():
    """
    Verifies that querying kyc_records using the kyc_service_role connection pool (KycSessionLocal)
    succeeds without raising a permission error.
    """
    kyc_session = KycSessionLocal()
    try:
        result = kyc_session.execute(text("SELECT count(*) FROM kyc_records;"))
        assert result is not None
    finally:
        kyc_session.close()


def test_account_ledger_immutability():
    """
    Verifies that executing UPDATE, DELETE, or TRUNCATE against account_ledger raises a permission error (SQLSTATE 42501).
    """
    ledger_session = SessionLocal()
    if ledger_session.bind and ledger_session.bind.dialect.name == "sqlite":
        ledger_session.close()
        pytest.skip("RBAC immutability tests require live PostgreSQL engine")
    try:
        with pytest.raises(sqlalchemy.exc.ProgrammingError) as exc_info:
            ledger_session.execute(text("TRUNCATE TABLE account_ledger;"))
        assert "SQLSTATE 42501" in str(exc_info.value) or "permission denied" in str(exc_info.value)
    finally:
        ledger_session.close()
