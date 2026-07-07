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

"""Test configuration module."""

import pytest
import sqlalchemy as _sa
from fastapi import Header, HTTPException

_orig_create_engine = _sa.create_engine


def _patched_create_engine(*args, **kwargs):
    if args and str(args[0]).startswith("sqlite"):
        exec_opts = kwargs.get("execution_options", {}).copy()
        if "schema_translate_map" not in exec_opts:
            exec_opts["schema_translate_map"] = {"merchants": "ref_data"}
        kwargs["execution_options"] = exec_opts
    elif "sqlite" in kwargs.get("url", "") or "sqlite" in str(kwargs.get("url_str", "")):
        exec_opts = kwargs.get("execution_options", {}).copy()
        if "schema_translate_map" not in exec_opts:
            exec_opts["schema_translate_map"] = {"merchants": "ref_data"}
        kwargs["execution_options"] = exec_opts
    return _orig_create_engine(*args, **kwargs)


_sa.create_engine = _patched_create_engine

from main import app  # noqa: E402
from models.authentication import ValidatedToken  # noqa: E402
from utils.auth import get_current_user  # noqa: E402


@pytest.fixture(autouse=True)
def override_test_auth():
    def mock_get_current_user(
        x_forwarded_user_context: str = Header(None),
        authorization: str = Header(None),
    ):
        token_str = None
        if authorization and authorization.startswith("Bearer "):
            token_str = authorization.split(" ")[1]
        elif x_forwarded_user_context and x_forwarded_user_context.startswith("Bearer "):
            token_str = x_forwarded_user_context.split(" ")[1]

        if token_str:
            if "invalid" in token_str.lower():
                raise HTTPException(status_code=401, detail="Invalid token")
            return ValidatedToken(claims={"sub": token_str, "email": f"{token_str}@example.com"})
        return ValidatedToken(claims={"sub": "mock_user_sub", "email": "mockuser@example.com"})

    previous_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    if previous_override is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous_override
