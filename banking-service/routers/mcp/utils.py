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

import os
import logging
import asyncio
import functools
import inspect
from contextvars import ContextVar
from pathlib import Path
from fastmcp import Context

from utils.auth import validate_firebase_token
from utils.env import is_running_locally
from utils.database import SessionLocal
from utils.log_safety import stable_log_reference
from services.action_proposal_context import ProposalRuntimeContext
from services.ces_session_capability import (
    CesSessionCapabilityError,
    validate_ces_session_capability,
)
from services.voice_session_epochs import get_reset_generation

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "sql"


def _load_sql(filename: str) -> str:
    """Loads a clean SQL query template from the resources directory."""
    return (SQL_DIR / filename).read_text()


def _extract_customer_identity(ctx: Context) -> str:
    """
    OIDC Context Extractor: Dynamically parses the authenticated user
    identity from IAP/OIDC headers in the underlying ASGI HTTP scope.
    """
    # If running in local test/mock suites without live requests context
    if not ctx or not ctx.request_context or not ctx.request_context.headers:
        logger.warning("Local/Mock run context: returning default testing customer ID.")
        return "customer-123"

    # Decode ASGI scope binary headers to UTF-8 string dictionary dynamically
    headers = {}
    for k, v in ctx.request_context.headers:
        headers[k.decode("utf-8").lower().strip()] = v.decode("utf-8").strip()

    # 1. Check standard Google Cloud IAP authenticated email header
    iap_header = headers.get("x-goog-authenticated-user-email")
    if iap_header:
        # Normalize standard Argolis/GCP email identity claims
        email = iap_header.replace("accounts.google.com:", "").strip()
        logger.info(
            "Identity verified via IAP header context identity_ref=%s",
            stable_log_reference(email, "identity"),
        )
        return email

    # 2. Check custom development authorization context header (strictly gated to Local Development environment)
    if (
        os.getenv("ALLOW_DEV_AUTH_BYPASS") == "true"
        or os.getenv("ENV") == "development"
    ):
        dev_auth = headers.get("x-forwarded-user-context") or headers.get(
            "authorization"
        )
        if dev_auth:
            # Development/Sandbox bypass parsing
            email = dev_auth.replace("Bearer ", "").strip()
            logger.info(
                "Identity verified via forwarded context identity_ref=%s",
                stable_log_reference(email, "identity"),
            )
            return email

    logger.error("Authentication context missing from ASGI request headers.")
    raise PermissionError(
        "Unauthorized: Identity context missing from request headers."
    )


def _mask_ssn(ssn_value: str) -> str:
    """Obfuscates Social Security Numbers to LAST_4 for log and context safety."""
    if not ssn_value:
        return "N/A"
    sanitized = ssn_value.replace("-", "").strip()
    if len(sanitized) >= 4:
        return f"***-**-{sanitized[-4:]}"
    return "***-**-****"


def _mask_ein(ein_value: str) -> str:
    """Obfuscates Employer Identification Numbers for context safety."""
    if not ein_value:
        return "N/A"
    sanitized = ein_value.replace("-", "").strip()
    if len(sanitized) >= 4:
        return f"**-***{sanitized[-4:]}"
    return "**-***-****"


verified_customer_id_var: ContextVar[str] = ContextVar(
    "verified_customer_id", default=None
)
assertion_token_var: ContextVar[str] = ContextVar("assertion_token", default=None)
proposal_runtime_context_var: ContextVar[ProposalRuntimeContext | None] = ContextVar(
    "proposal_runtime_context", default=None
)
PROPOSAL_CONTEXT_TOOL_NAMES = frozenset({"propose_fraud_triage", "commit_fraud_triage"})


def _proposal_context_for_tool(
    tool_name: str, headers: dict[str, str]
) -> ProposalRuntimeContext | None:
    """Parse protected proposal headers only for proposal lifecycle tools."""
    if tool_name not in PROPOSAL_CONTEXT_TOOL_NAMES:
        return None
    return ProposalRuntimeContext.from_headers(headers)


def _identity_from_ces_capability(capability: str, headers: dict[str, str]) -> str:
    """Validate one CES capability and its current reset generation."""
    claims = validate_ces_session_capability(capability, headers)
    if claims.runtime_name != "CES_GEMINI_LIVE":
        raise CesSessionCapabilityError("CES session capability runtime is invalid.")

    db = SessionLocal()
    try:
        current_generation = str(
            get_reset_generation(db, claims.customer_id).get("token") or ""
        )
    finally:
        db.close()
    if current_generation != claims.reset_generation:
        raise CesSessionCapabilityError(
            "CES session capability was invalidated by a demo reset."
        )
    return claims.customer_identity


def requires_user_assertion(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        is_support = True  # Default to True locally

        # 1. Verify Caller Identity (Google OIDC ID Token)
        ctx = kwargs.get("ctx") or (
            args[-1] if args and isinstance(args[-1], Context) else None
        )
        if not ctx:
            logger.warning(
                "No FastMCP Context passed to decorator, bypassing caller validation."
            )
        else:
            headers = {}
            if ctx.request_context and ctx.request_context.request:
                headers = {
                    k.lower().strip(): v.strip()
                    for k, v in ctx.request_context.request.headers.items()
                }

            if not is_running_locally():
                auth_header = headers.get("authorization", "")
                if not auth_header or not auth_header.startswith("Bearer "):
                    logger.error(
                        "Missing or invalid Authorization header in FastMCP invocation."
                    )
                    raise PermissionError(
                        "Access Denied: Missing or invalid Authorization header."
                    )

                token = auth_header.split("Bearer ")[1].strip()
                try:
                    from utils.auth import validate_google_id_token, is_support_staff

                    caller_token = validate_google_id_token(token)
                    is_support = is_support_staff(caller_token)
                except Exception as exc:
                    logger.error(
                        "GECX caller token verification failed error_type=%s",
                        type(exc).__name__,
                    )
                    raise PermissionError(
                        "Access Denied: GECX caller token verification failed."
                    ) from exc

        # 2. Extract and validate Firebase ID Token Assertion or resolve target customer ID for support staff
        headers = {}
        if ctx and ctx.request_context and ctx.request_context.request:
            headers = {
                k.lower().strip(): v.strip()
                for k, v in ctx.request_context.request.headers.items()
            }

        target_customer_id = headers.get("x-target-customer-id")
        session_capability = headers.get("x-banking-session-capability")
        effective_id = None
        assertion_token = None

        if session_capability:
            if not is_support:
                raise PermissionError(
                    "Access Denied: CES capability requires an authorized service caller."
                )
            try:
                effective_id = _identity_from_ces_capability(
                    session_capability, headers
                )
            except Exception as exc:
                logger.error(
                    "CES session capability validation failed tool=%s error_type=%s",
                    func.__name__,
                    type(exc).__name__,
                )
                raise PermissionError(
                    "Access Denied: Invalid CES session capability."
                ) from exc
            logger.info(
                "FastMCP invocation authorized tool=%s support_caller=true "
                "target_customer_ref=%s capability_present=true",
                func.__name__,
                stable_log_reference(effective_id, "customer"),
            )
        elif is_support and target_customer_id:
            logger.info(
                "FastMCP invocation authorized tool=%s support_caller=true "
                "target_customer_ref=%s assertion_present=false",
                func.__name__,
                stable_log_reference(target_customer_id, "customer"),
            )
            effective_id = target_customer_id
        else:
            assertion_token = headers.get("x-forwarded-user-context") or kwargs.get(
                "assertion_token"
            )
            if not assertion_token:
                raise ValueError(
                    "Missing Firebase user assertion token (must be passed in 'x-forwarded-user-context' header or 'assertion_token' argument)."
                )

            user_id = None
            if is_running_locally() and assertion_token == "mock-local-token":
                user_id = "mock_user_id"
            else:
                try:
                    validated = validate_firebase_token(assertion_token)
                    user_id = validated.claims.get("sub")
                except Exception as exc:
                    logger.error(
                        "Firebase token validation failed in FastMCP error_type=%s",
                        type(exc).__name__,
                    )
                    raise PermissionError(
                        "Access Denied: Invalid assertion token."
                    ) from exc

            # 3. Resolve customer ID with Demo Fallback support
            db = SessionLocal()
            from repositories.credit_card import CreditCardRepository

            repo = CreditCardRepository(db)
            try:
                effective_id = user_id
                account = repo.get_account_by_customer(user_id)
                if not account:
                    enable_fallback = (
                        os.getenv("ENABLE_DEMO_FALLBACK", "true").lower() == "true"
                    )
                    if enable_fallback:
                        accounts = repo.get_all_accounts()
                        if accounts:
                            effective_id = str(accounts[0].customer_id)
                            logger.warning(
                                "Customer profile not seeded; using demo fallback "
                                "requested_customer_ref=%s effective_customer_ref=%s",
                                stable_log_reference(user_id, "customer"),
                                stable_log_reference(effective_id, "customer"),
                            )
                        else:
                            raise ValueError(
                                f"No financial account found for customer ID '{user_id}' and no seeded accounts exist."
                            )
                    else:
                        raise ValueError(
                            f"No financial account found for customer ID '{user_id}'."
                        )
            finally:
                db.close()

            logger.info(
                "FastMCP invocation authorized tool=%s support_caller=%s "
                "target_customer_ref=%s assertion_present=%s",
                func.__name__,
                str(is_support).lower(),
                stable_log_reference(effective_id, "customer"),
                bool(assertion_token),
            )

        # Set ContextVars for internal resolution
        t_cust = verified_customer_id_var.set(effective_id)
        t_assert = assertion_token_var.set(assertion_token)
        runtime_context = _proposal_context_for_tool(func.__name__, headers)
        t_runtime = proposal_runtime_context_var.set(runtime_context)

        try:
            # Check wrapped function signature and dynamically inject kwargs if declared
            sig = inspect.signature(func)
            if "verified_customer_id" in sig.parameters:
                kwargs["verified_customer_id"] = effective_id
            else:
                kwargs.pop("verified_customer_id", None)

            if "assertion_token" in sig.parameters:
                kwargs["assertion_token"] = assertion_token
            else:
                kwargs.pop("assertion_token", None)

            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        finally:
            proposal_runtime_context_var.reset(t_runtime)
            verified_customer_id_var.reset(t_cust)
            assertion_token_var.reset(t_assert)

    return wrapper
