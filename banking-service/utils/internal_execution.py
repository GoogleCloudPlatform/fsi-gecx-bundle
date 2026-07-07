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
