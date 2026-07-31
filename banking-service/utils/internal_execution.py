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

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from utils.database import enable_session_rbac_override
from utils.internal_auth import require_internal_switch_token


@dataclass(frozen=True)
class InternalServiceContext:
    principal: str
    scope: str

    def require_scope(self, scope: str) -> None:
        if self.scope != scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Internal caller '{self.principal}' is not authorized for scope '{scope}'.",
            )


def require_internal_simulation_context(
    x_card_network_token: str | None = Header(None, alias="X-Card-Network-Token"),
) -> InternalServiceContext:
    require_internal_switch_token(x_card_network_token)
    return InternalServiceContext(principal="data-generator", scope="simulation:autopaydown")


def apply_internal_db_access(db: Session, context: InternalServiceContext, scope: str) -> None:
    context.require_scope(scope)
    enable_session_rbac_override(db)
