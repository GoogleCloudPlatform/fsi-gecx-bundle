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

"""Profile preferences are persisted per authenticated customer, never by a voice override."""
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.identity import User
from models.profile import CustomerProfileUpdateRequest
from repositories.identity import get_customer, update_customer
from utils.database import Base
from utils.support_locale import resolve_support_locale


@pytest.fixture
def profile_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            yield db
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_profile_language_persistence_preservation_and_customer_isolation(profile_db):
    db = profile_db
    db.add_all([User(auth_provider_uid="alice"), User(auth_provider_uid="bob")])
    db.commit()
    assert get_customer(db, "alice")["preferred_support_locale"] == "en-US"
    update_customer(db, "alice", None, None, None, "es-MX")
    db.expire_all()
    assert get_customer(db, "alice")["preferred_support_locale"] == "es-MX"
    assert get_customer(db, "bob")["preferred_support_locale"] == "en-US"
    update_customer(db, "alice", "Alice", None, None)
    assert get_customer(db, "alice")["preferred_support_locale"] == "es-MX"


@pytest.mark.parametrize("value", ["es", "fr-FR", "", 42])
def test_profile_rejects_unsupported_locales(value):
    with pytest.raises(ValidationError):
        CustomerProfileUpdateRequest(preferred_support_locale=value)
    with pytest.raises(ValueError):
        resolve_support_locale("en-US", value)


def test_omitted_or_null_preference_does_not_replace_saved_value():
    assert CustomerProfileUpdateRequest().preferred_support_locale is None
    assert CustomerProfileUpdateRequest(preferred_support_locale=None).preferred_support_locale is None
    assert resolve_support_locale("es-MX") == "es-MX"
    assert resolve_support_locale(None) == "en-US"


@pytest.mark.parametrize("override,expected", [(None, "es-MX"), ("en-US", "en-US")])
def test_adk_dispatch_uses_profile_default_or_explicit_override(override, expected):
    from unittest.mock import MagicMock, patch
    from fastapi import BackgroundTasks
    from models.authentication import ValidatedToken
    from routers.credit_card import get_voice_room_token
    tasks = BackgroundTasks()
    with patch("routers.credit_card.identity_repo.get_customer", return_value={"preferred_support_locale": "es-MX"}) as profile, \
         patch("routers.credit_card.lk_api.AccessToken"), \
         patch("routers.credit_card.FraudAlertService") as fraud:
        fraud.return_value.get_active_voice_context.return_value = {}
        get_voice_room_token(tasks, locale=override, db=MagicMock(), customer_id="alice", caller=ValidatedToken(claims={"sub":"alice"}))
    profile.assert_called_once()
    assert profile.call_args.args[1] == "alice"
    assert tasks.tasks[0].args[-1] == expected
