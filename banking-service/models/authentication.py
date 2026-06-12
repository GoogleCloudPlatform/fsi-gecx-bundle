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

from enum import Enum

from pydantic import BaseModel


class ForwardedUserContextType(str, Enum):
    CXAS_AGENT = "cxas-agent"


class TokenValidateRequest(BaseModel):
    token: str


class ValidatedToken(BaseModel):
    claims: dict

    @property
    def user_id(self) -> str | None:
        return self.claims.get("identifier") or self.claims.get("sub")

    @property
    def email(self) -> str | None:
        return self.claims.get("email")

    @property
    def name(self) -> str | None:
        return self.claims.get("name")

    @property
    def expiry_time(self) -> int | None:
        return self.claims.get("exp")

    @property
    def audience(self) -> str | None:
        return self.claims.get("aud")

    @property
    def issuer(self) -> str | None:
        return self.claims.get("iss")

    @classmethod
    def get_mock_token(cls):
        return cls(claims={"sub": "mock_user_sub", "email": "mockuser@example.com"})
