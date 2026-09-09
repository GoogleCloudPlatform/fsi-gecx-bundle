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

"""Money tests must never use cloud/network services."""

import os
from pathlib import Path
import sys
import socket
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "banking-service"))
os.environ["DISABLE_INIT_DB"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LEDGER_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["KYC_DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Money unit tests must not open network connections")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)


@pytest.fixture
def db_session():
    import importlib
    from sqlalchemy.orm import Session
    from utils.database import Base, create_db_engine
    for name in ("identity", "origination", "audit", "credit_card", "fraud", "support",
                 "action_proposal", "settings", "kyc", "reference", "merchant"):
        importlib.import_module(f"models.{name}")
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()
