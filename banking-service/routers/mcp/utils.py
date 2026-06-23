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
from pathlib import Path
from fastmcp import Context

from utils.auth import validate_firebase_token
from utils.env import is_running_locally
from utils.database import SessionLocal

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
        logger.info(f"Identity verified via IAP header context: {email}")
        return email
        
    # 2. Check custom development authorization context header (strictly gated to Local Development environment)
    if os.getenv("ALLOW_DEV_AUTH_BYPASS") == "true" or os.getenv("ENV") == "development":
        dev_auth = headers.get("x-forwarded-user-context") or headers.get("authorization")
        if dev_auth:
            # Development/Sandbox bypass parsing
            email = dev_auth.replace("Bearer ", "").strip()
            logger.info(f"Identity verified via Forwarded Context: {email}")
            return email
        
    logger.error("Authentication context missing from ASGI request headers.")
    raise PermissionError("Unauthorized: Identity context missing from request headers.")

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


def requires_user_assertion(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 1. Verify Caller Identity (Google OIDC ID Token)
        ctx = kwargs.get("ctx") or (args[-1] if args and isinstance(args[-1], Context) else None)
        if not ctx:
            logger.warning("No FastMCP Context passed to decorator, bypassing caller validation.")
        else:
            headers = {}
            if ctx.request_context and ctx.request_context.request:
                headers = {k.lower().strip(): v.strip() for k, v in ctx.request_context.request.headers.items()}
            
            if not is_running_locally():
                auth_header = headers.get("authorization", "")
                if not auth_header or not auth_header.startswith("Bearer "):
                    logger.error("Missing or invalid Authorization header in FastMCP invocation.")
                    raise PermissionError("Access Denied: Missing or invalid Authorization header.")
                
                token = auth_header.split("Bearer ")[1].strip()
                try:
                    from utils.auth import validate_google_id_token
                    validate_google_id_token(token)
                except Exception as e:
                    logger.error(f"GECX caller token verification failed: {e}")
                    raise PermissionError("Access Denied: GECX caller token verification failed.")

        # 2. Extract and validate Firebase ID Token Assertion
        logger.info(f"FastMCP call kwargs: {kwargs}")
        logger.info(f"FastMCP call ctx: {ctx.__dict__ if ctx else None}")
        
        headers = {}
        if ctx and ctx.request_context and ctx.request_context.request:
            headers = {k.lower().strip(): v.strip() for k, v in ctx.request_context.request.headers.items()}
        
        logger.info(f"FastMCP call headers: {headers}")
            
        assertion_token = headers.get("x-forwarded-user-context") or kwargs.get("assertion_token")
        if not assertion_token:
            raise ValueError("Missing Firebase user assertion token (must be passed in 'x-forwarded-user-context' header or 'assertion_token' argument).")

        user_id = None
        if is_running_locally() and assertion_token == "mock-local-token":
            user_id = "mock_user_id"
        else:
            try:
                validated = validate_firebase_token(assertion_token)
                user_id = validated.claims.get("sub")
            except Exception as e:
                logger.error(f"Firebase token validation failed in FastMCP: {e}")
                raise PermissionError(f"Access Denied: Invalid assertion token. Details: {e}")

        # 3. Resolve customer ID with Demo Fallback support
        db = SessionLocal()
        from repositories.credit_card import CreditCardRepository
        repo = CreditCardRepository(db)
        try:
            effective_id = user_id
            account = repo.get_account_by_customer(user_id)
            if not account:
                enable_fallback = os.getenv("ENABLE_DEMO_FALLBACK", "true").lower() == "true"
                if enable_fallback:
                    logger.warning(f"Customer profile '{user_id}' not seeded. Falling back to 'cust-123' for demo purposes.")
                    effective_id = "cust-123"
                else:
                    raise ValueError(f"No financial account found for customer ID '{user_id}'.")
            
            kwargs["verified_customer_id"] = effective_id
        finally:
            db.close()

        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)
            
    return wrapper
