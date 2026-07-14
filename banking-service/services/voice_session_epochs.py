"""Reset-generation authority for persistent voice-support sessions."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

SCHEMA = "voice_support_sessions"


def _supports_epochs(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def get_reset_generation(db: Session, customer_id: str) -> dict[str, int | str]:
    """Return the global and presenter epochs as an opaque generation token."""
    if not _supports_epochs(db):
        return {"global_epoch": 0, "customer_epoch": 0, "token": "0:0"}
    rows = db.execute(
        text(
            f"""
            SELECT scope_type, epoch
            FROM {SCHEMA}.reset_epochs
            WHERE (scope_type = 'GLOBAL' AND scope_id = '*')
               OR (scope_type = 'CUSTOMER' AND scope_id = :customer_id)
            """
        ),
        {"customer_id": customer_id},
    ).all()
    epochs = {scope_type: int(epoch) for scope_type, epoch in rows}
    global_epoch = epochs.get("GLOBAL", 0)
    customer_epoch = epochs.get("CUSTOMER", 0)
    return {
        "global_epoch": global_epoch,
        "customer_epoch": customer_epoch,
        "token": f"{global_epoch}:{customer_epoch}",
    }


def bump_customer_reset_generation(db: Session, customer_id: str) -> None:
    if not _supports_epochs(db):
        return
    db.execute(
        text(
            f"""
            INSERT INTO {SCHEMA}.reset_epochs (scope_type, scope_id, epoch)
            VALUES ('CUSTOMER', :customer_id, 1)
            ON CONFLICT (scope_type, scope_id) DO UPDATE
            SET epoch = {SCHEMA}.reset_epochs.epoch + 1,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"customer_id": customer_id},
    )
    db.commit()


def bump_global_reset_generation(db: Session) -> None:
    if not _supports_epochs(db):
        return
    db.execute(
        text(
            f"""
            INSERT INTO {SCHEMA}.reset_epochs (scope_type, scope_id, epoch)
            VALUES ('GLOBAL', '*', 1)
            ON CONFLICT (scope_type, scope_id) DO UPDATE
            SET epoch = {SCHEMA}.reset_epochs.epoch + 1,
                updated_at = CURRENT_TIMESTAMP
            """
        )
    )
    db.commit()
