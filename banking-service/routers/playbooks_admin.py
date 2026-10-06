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

"""Authenticated operator interface for bank-owned playbook definitions."""

from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session
from models.authentication import ValidatedToken
from models.playbook import CHANGE_REQUEST_DESCRIPTION_MAX, CHANGE_REQUEST_TITLE_MAX
from services.playbook_administration import PlaybookAdministration
from services.playbook_repository import (
    RepositoryError,
    PlaybookNotFound,
    PlaybookConflict,
)
from utils.auth import require_admin_user
from utils.database import get_db

router = APIRouter(
    prefix="/admin/playbooks",
    tags=["Playbook Administration"],
    dependencies=[Depends(require_admin_user)],
)


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeRequestText(StrictDTO):
    title: str | None = Field(None, min_length=1, max_length=CHANGE_REQUEST_TITLE_MAX)
    description: str | None = Field(None, max_length=CHANGE_REQUEST_DESCRIPTION_MAX)


class CreatePlaybook(ChangeRequestText):
    document: dict[str, Any]


class DraftSource(ChangeRequestText):
    source_revision: StrictInt = Field(ge=1)
    expected_generation: StrictInt = Field(ge=0)


class RestoreRevision(ChangeRequestText):
    expected_generation: StrictInt = Field(ge=0)


class UpdateChangeRequest(ChangeRequestText):
    expected_version: StrictInt = Field(ge=1)


class DraftVersion(StrictDTO):
    expected_draft_version: StrictInt = Field(ge=1)


class EditDraft(DraftVersion):
    document: dict[str, Any]


class PublishDraft(DraftVersion):
    expected_generation: StrictInt = Field(ge=0)


class RecreateFromHead(PublishDraft):
    pass


def get_administration(db: Session = Depends(get_db)):
    return PlaybookAdministration(db)


def call(operation):
    try:
        return operation()
    except RepositoryError as exc:
        status = (
            404
            if isinstance(exc, PlaybookNotFound)
            else 409
            if isinstance(exc, PlaybookConflict)
            else 422
        )
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": str(exc)}
        ) from exc


def actor(token):
    return str(
        token.claims.get("sub")
        or token.claims.get("identifier")
        or token.email
        or "authenticated-operator"
    )[:255]


@router.get("")
def list_playbooks(service: PlaybookAdministration = Depends(get_administration)):
    return call(service.list)


@router.get("/capabilities")
def capabilities(service: PlaybookAdministration = Depends(get_administration)):
    return call(service.capabilities)


@router.get("/policy")
def policy(service: PlaybookAdministration = Depends(get_administration)):
    return call(service.policy_view)


@router.post("", status_code=201)
def create(
    payload: CreatePlaybook,
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.create(
            payload.document, actor(token), payload.title, payload.description
        )
    )


@router.get("/{playbook_id}/revisions/{revision}")
def get_revision(
    playbook_id: str,
    revision: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
):
    return call(lambda: service.get(playbook_id, revision))


@router.post("/{playbook_id}/revisions/{revision}/restore", status_code=201)
def restore_revision(
    playbook_id: str,
    payload: RestoreRevision,
    revision: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.restore(
            playbook_id,
            revision,
            payload.expected_generation,
            actor(token),
            payload.title,
            payload.description,
        )
    )


@router.get("/{playbook_id}/history")
def history(
    playbook_id: str,
    service: PlaybookAdministration = Depends(get_administration),
):
    return call(lambda: service.history(playbook_id))


@router.post("/{playbook_id}/drafts", status_code=201)
def create_draft(
    playbook_id: str,
    payload: DraftSource,
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.create_draft(
            playbook_id,
            payload.source_revision,
            payload.expected_generation,
            actor(token),
            payload.title,
            payload.description,
        )
    )


@router.put("/{playbook_id}/drafts/{revision}")
def edit_draft(
    playbook_id: str,
    payload: EditDraft,
    revision: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.edit(
            playbook_id,
            revision,
            payload.document,
            payload.expected_draft_version,
            actor(token),
        )
    )


@router.post("/{playbook_id}/drafts/{revision}/validate")
def validate_draft(
    playbook_id: str,
    payload: DraftVersion,
    revision: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
):
    return call(
        lambda: service.validate(playbook_id, revision, payload.expected_draft_version)
    )


@router.post("/{playbook_id}/drafts/{revision}/publish")
def publish_draft(
    playbook_id: str,
    payload: PublishDraft,
    revision: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.publish(
            playbook_id,
            revision,
            payload.expected_draft_version,
            payload.expected_generation,
            actor(token),
        )
    )


@router.get("/{playbook_id}/change-requests")
def list_change_requests(
    playbook_id: str,
    status: Literal["OPEN", "PUBLISHED", "CLOSED"] | None = Query(None),
    service: PlaybookAdministration = Depends(get_administration),
):
    return call(lambda: service.change_requests(playbook_id, status))


@router.get("/{playbook_id}/change-requests/{change_request_id}")
def change_request_detail(
    playbook_id: str,
    change_request_id: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
):
    return call(lambda: service.change_request_detail(playbook_id, change_request_id))


@router.patch("/{playbook_id}/change-requests/{change_request_id}")
def update_change_request(
    playbook_id: str,
    payload: UpdateChangeRequest,
    change_request_id: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.update_change_request(
            playbook_id,
            change_request_id,
            payload.expected_version,
            actor(token),
            payload.title,
            payload.description,
        )
    )


@router.post("/{playbook_id}/change-requests/{change_request_id}/close")
def close_change_request(
    playbook_id: str,
    change_request_id: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.close_change_request(
            playbook_id, change_request_id, actor(token)
        )
    )


@router.post(
    "/{playbook_id}/change-requests/{change_request_id}/recreate-from-head",
    status_code=201,
)
def recreate_from_head(
    playbook_id: str,
    payload: RecreateFromHead,
    change_request_id: int = Path(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
    token: ValidatedToken = Depends(require_admin_user),
):
    return call(
        lambda: service.recreate_from_head(
            playbook_id,
            change_request_id,
            payload.expected_draft_version,
            payload.expected_generation,
            actor(token),
        )
    )


@router.get("/{playbook_id}/compare")
def compare(
    playbook_id: str,
    from_revision: int = Query(ge=1),
    to_revision: int = Query(ge=1),
    service: PlaybookAdministration = Depends(get_administration),
):
    return call(lambda: service.compare(playbook_id, from_revision, to_revision))
