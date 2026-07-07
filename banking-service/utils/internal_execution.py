from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session


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
    switch_token = os.getenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
    if not x_card_network_token or x_card_network_token != switch_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized internal simulation invocation.",
        )
    return InternalServiceContext(principal="data-generator", scope="simulation:autopaydown")


def apply_internal_db_access(db: Session, context: InternalServiceContext, scope: str) -> None:
    context.require_scope(scope)

    if hasattr(db.bind, "engine"):
        db.bind.engine._ignore_rbac = True
    else:
        db.bind._ignore_rbac = True

    db.connection().info["_ignore_rbac"] = True
