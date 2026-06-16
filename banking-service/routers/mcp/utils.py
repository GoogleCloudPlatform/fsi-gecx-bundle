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
from pathlib import Path
from fastmcp import Context

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
