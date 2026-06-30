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

import uuid
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from models.identity import User
from models.origination import Application, ApplicationArtifact
from utils.audit import record_audit_event

logger = logging.getLogger(__name__)


def log_application(
    db: Session,
    auth_provider_uid: str,
    product_category: str,
    product_type: str,
    requested_amount: Optional[float],
) -> str:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        user = User(auth_provider_uid=auth_provider_uid)
        db.add(user)
        db.flush()

    app_ext_id = f"APP-{uuid.uuid4()}"
    amount_cents = int(requested_amount * 100) if requested_amount is not None else None

    app = Application(
        application_id=app_ext_id,
        user_id=user.id,
        product_category=product_category or product_type or "GENERAL",
        status="SUBMITTED",
        requested_amount_cents=amount_cents,
    )
    db.add(app)
    db.flush()

    record_audit_event(
        db,
        "APPLICATION_CREATED",
        {
            "application_id": app_ext_id,
            "user_id": auth_provider_uid,
            "product_category": product_category,
            "requested_amount": requested_amount,
        },
    )
    db.commit()
    return app_ext_id


def update_application(
    db: Session,
    application_id: str,
    auth_provider_uid: str,
    requested_amount: Optional[float],
    application_status: Optional[str],
) -> None:
    app = db.query(Application).filter(Application.application_id == application_id).first()
    if not app:
        logger.warning(f"Application {application_id} not found for update.")
        return

    if requested_amount is not None:
        app.requested_amount_cents = int(requested_amount * 100)
    if application_status is not None:
        app.status = application_status

    record_audit_event(
        db,
        "APPLICATION_UPDATED",
        {
            "application_id": application_id,
            "user_id": auth_provider_uid,
            "requested_amount": requested_amount,
            "status": application_status,
        },
    )
    db.commit()


def log_artifact(
    db: Session,
    application_id: str,
    artifact_type: str,
    gcs_uri: str,
    auth_provider_uid: str,
    artifact_id: str,
) -> str:
    user = db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()
    if not user:
        user = User(auth_provider_uid=auth_provider_uid)
        db.add(user)
        db.flush()

    app = db.query(Application).filter(Application.application_id == application_id).first()
    if not app:
        # Create placeholder application if artifact uploaded before application record exists
        app = Application(
            application_id=application_id,
            user_id=user.id,
            product_category="GENERAL",
            status="STARTED",
        )
        db.add(app)
        db.flush()

    art = ApplicationArtifact(
        artifact_id=artifact_id,
        application_id=app.id,
        customer_id=user.id,
        claimed_artifact_type=artifact_type,
        gcs_uri=gcs_uri,
        status="UPLOADED",
    )
    db.add(art)
    db.flush()

    record_audit_event(
        db,
        "ARTIFACT_UPLOADED",
        {
            "artifact_id": artifact_id,
            "application_id": application_id,
            "user_id": auth_provider_uid,
            "gcs_uri": gcs_uri,
        },
    )
    db.commit()
    return artifact_id


def get_application(db: Session, application_id: str) -> Optional[Dict[str, Any]]:
    app = db.query(Application).filter(Application.application_id == application_id).first()
    if not app:
        return None
    return {
        "application_id": app.application_id,
        "user_id": app.user.auth_provider_uid if app.user else None,
        "product_category": app.product_category,
        "status": app.status,
        "requested_amount": app.requested_amount_cents / 100.0 if app.requested_amount_cents is not None else None,
        "started_at": app.started_at.isoformat() if app.started_at else None,
    }
