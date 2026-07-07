import os

from fastapi import HTTPException, status

from utils.runtime import is_local_dev


def get_internal_switch_token() -> str:
    token = os.getenv("CARD_NETWORK_SWITCH_TOKEN")
    if token:
        return token
    if is_local_dev():
        return "switch-secret-key-12345"
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Data generator is not configured.",
    )


def is_valid_internal_switch_token(candidate: str | None) -> bool:
    return bool(candidate) and candidate == get_internal_switch_token()
