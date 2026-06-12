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

from fastapi import Header, HTTPException
import pytest

from main import app
from utils.auth import get_current_user
from models.authentication import ValidatedToken






@pytest.fixture(autouse=True)
def override_test_auth():
    def mock_get_current_user(
            x_forwarded_user_context: str = Header(None),
            authorization: str = Header(None)
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

    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.clear()
