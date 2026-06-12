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

import base64
import json
import logging
import os
import time
from typing import Annotated

from fastapi import Header, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth as firebase_auth
from google.auth.transport import requests
from google.oauth2 import id_token
from joserfc import jwk, jwt

from models.authentication import ValidatedToken, ForwardedUserContextType
from models.security import HTTPForwardedBearer
from utils.auth_config import ALLOWED_FORWARDED_AUTH_ROUTES
from utils.env import is_running_locally
from utils.gcp import get_secret, get_project_id

PROJECT_ID = get_project_id()
logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)
forwarded_bearer_scheme = HTTPForwardedBearer(auto_error=False)

SERVICE_NAME = "banking-service"
SUPPORT_DOMAINS = os.getenv("SUPPORT_EMAIL_DOMAINS", "google.com,novahorizon.com").split(",")

def is_support_staff(token: ValidatedToken) -> bool:
    if not token or not hasattr(token, "claims"):
        return False
    email = token.claims.get("email")
    if not email:
        return False
    
    # Check if voice agent service account
    if email == f"voice-agent-sa@{PROJECT_ID}.iam.gserviceaccount.com":
        return True

    # Check domain suffix or specific mock profiles
    domain = email.split("@")[-1]
    if domain in SUPPORT_DOMAINS or email == "underwriter@nova.horizon":
        return True
    return False


def mint_cxas_token(user_data: ValidatedToken) -> dict:
    try:
        client_secret = get_secret("iap-client-secret")
        client_id = get_secret("iap-client-id")
    except Exception as e:
        logger.error(f"Error getting IAP secrets from Secret Manager: {e}")
        raise HTTPException(status_code=500, detail="Server configuration error")

    secret_key = jwk.OctKey.import_key(client_secret)

    now = int(time.time())
    payload = {
        'iss': SERVICE_NAME,
        "aud": SERVICE_NAME,
        "client_id": client_id,
        'iat': now,
        'exp': now + 3600,
    }

    # Use values from verified IAP JWT
    if user_data:
        payload['identifier'] = user_data.user_id
        payload['sub'] = user_data.user_id
        payload['name'] = user_data.name
        payload['email'] = user_data.email
        payload['type'] = ForwardedUserContextType.CXAS_AGENT.value

    token = jwt.encode({'alg': 'HS256'}, payload, secret_key)
    return {'token': token}


def validate_cxas_token(jwt_token: str) -> ValidatedToken:
    try:
        secret_key = get_secret("iap-client-secret")
        expected_client_id = get_secret("iap-client-id")
    except Exception as e:
        logger.error(f"Error getting IAP secret from Secret Manager: {e}")
        raise HTTPException(status_code=500, detail="Server configuration error")

    secret_key = jwk.OctKey.import_key(secret_key)

    try:
        decoded_token = jwt.decode(jwt_token, secret_key)
        claims = decoded_token.claims

        # 1. Validate Issuer
        if claims.get("iss") != SERVICE_NAME:
            raise HTTPException(status_code=401, detail="Invalid token issuer")

        # 2. Validate Audience
        if claims.get("aud") != SERVICE_NAME:
            raise HTTPException(status_code=401, detail="Invalid token audience")

        # 3. Validate Client ID
        if claims.get("client_id") != expected_client_id:
            raise HTTPException(status_code=401, detail="Invalid client ID")

        # 4. Validate Type
        if claims.get("type") != ForwardedUserContextType.CXAS_AGENT.value:
            raise HTTPException(status_code=401, detail="Invalid token type")

        return ValidatedToken(claims=claims)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def validate_iap_token(
        jwt_token: str | None, throws_error: bool = True
) -> ValidatedToken | None:
    """
    Validates a JWT token assertion from Google IAP.
    
    Args:
        jwt_token: The signed JWT token from the x-goog-iap-jwt-assertion header.
        throws_error: Whether to raise HTTPException on failure.

    Returns:
        ValidatedToken | None: The decoded JWT claims, or None if validation fails and throws_error is False.
        
    Raises:
        HTTPException: If verification fails or claims are invalid (only if throws_error is True).
    """
    if not jwt_token:
        if throws_error:
            raise HTTPException(
                status_code=401,
                detail="Missing IAP JWT assertion header"
            )
        return None

    expected_audiences_str = os.getenv("IAP_AUDIENCES", "")
    expected_audiences: list[str] = [a.strip() for a in expected_audiences_str.split(",") if a.strip()]

    if not expected_audiences:
        logger.error("IAP_AUDIENCES environment variable not set on backend")
        raise HTTPException(
            status_code=500,
            detail="IAP_AUDIENCES environment variable not set on backend"
        )

    try:
        # Verify the token using Google's public keys
        decoded_jwt = id_token.verify_token(
            jwt_token,
            requests.Request(),
            audience=expected_audiences,
            certs_url="https://www.gstatic.com/iap/verify/public_key"
        )

        # Validate audience
        if decoded_jwt.get("aud") not in expected_audiences:
            raise ValueError(f"Audience mismatch: expected one of {expected_audiences}, got {decoded_jwt.get('aud')}")

        # Validate the issuer (optional but recommended)
        if decoded_jwt.get('iss') != 'https://cloud.google.com/iap':
            raise ValueError('Invalid issuer')

        return ValidatedToken(claims=decoded_jwt)
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        if throws_error:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid IAP JWT: {e}"
            )
        return None


def validate_firebase_token(jwt_token: str) -> ValidatedToken:
    """
    Verifies the Firebase ID token passed from the frontend.
    """
    try:
        decoded_token = firebase_auth.verify_id_token(jwt_token)
        claims = {
            'iss': 'https://securetoken.google.com/' + decoded_token.get('aud', ''),
            'aud': decoded_token.get('aud'),
            'sub': decoded_token.get('uid'),
            'identifier': decoded_token.get('uid'),
            'email': decoded_token.get('email'),
            'name': decoded_token.get('name'),
            'exp': decoded_token.get('exp')
        }
        return ValidatedToken(claims=claims)
    except Exception as e:
        logger.warning(f"Firebase ID token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired authentication credentials.")


def validate_google_id_token(jwt_token: str) -> ValidatedToken:
    """
    Validates a Google ID token (e.g., from a service agent).
    """
    expected_audiences_str = os.getenv("IAP_AUDIENCES", "")
    expected_audiences: list[str] = [a.strip() for a in expected_audiences_str.split(",") if a.strip()]

    if not is_running_locally() and not expected_audiences:
        logger.error("IAP_AUDIENCES environment variable not set on backend")
        raise HTTPException(
            status_code=500,
            detail="IAP_AUDIENCES environment variable not set on backend"
        )

    try:
        # Verify the token using Google's public keys
        # We don't pass certs_url, so it defaults to Google's standard public keys
        decoded_jwt = id_token.verify_token(
            jwt_token,
            requests.Request(),
            # audience=expected_audiences, # Audience will be different for each endpoint
        )

        email = decoded_jwt.get('email', '')
        allowed_sa = f"voice-agent-sa@{PROJECT_ID}.iam.gserviceaccount.com"
        if not (email.endswith('@gcp-sa-ces.iam.gserviceaccount.com') or email == allowed_sa):
            raise ValueError('Invalid email domain or unauthorized service account')

        return ValidatedToken(claims=decoded_jwt)
    except Exception as e:
        logger.warning(f"Google ID token validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_unverified_claims(token: str) -> dict:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload).decode('utf-8')
        return json.loads(decoded)
    except Exception:
        return {}


def validate_token_by_issuer(token: str) -> ValidatedToken:
    claims = get_unverified_claims(token)
    iss = claims.get("iss", "")
    expected_firebase_iss = f"https://securetoken.google.com/{PROJECT_ID}"
    expected_google_id_iss = "https://accounts.google.com"

    if iss == expected_google_id_iss:
        return validate_google_id_token(token)
    elif iss == expected_firebase_iss:
        return validate_firebase_token(token)
    else:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


def is_route_allowed(method: str, path: str, context_type: str | None) -> bool:
    if not context_type:
        return False
    allowed_routes = ALLOWED_FORWARDED_AUTH_ROUTES.get(context_type, [])

    path = path.rstrip("/")
    for route in allowed_routes:
        route_path = route["path"].rstrip("/")
        if route["method"] == method:
            if path == route_path or path.endswith(route_path):
                return True
    return False


async def get_current_user(
        request: Request,
        # x_goog_iap_jwt_assertion: Annotated[str | None, Header()] = None,
        # x_forwarded_user_context: Annotated[str | None, Header()] = None,
        auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
        forwarded_auth: Annotated[HTTPAuthorizationCredentials | None, Depends(forwarded_bearer_scheme)] = None,
) -> ValidatedToken:
    called_path = request.url.path
    called_method = request.method
    # logger.info(f"Authenticating request for {called_method} {called_path}")

    # 1. Check for custom X-Forwarded-User-Context: Bearer <Token>
    # This is for the CX Agent Pass-through which authenticates to Cloud Run with an Authentication header
    # passed for the calling service account.
    if forwarded_auth and forwarded_auth.credentials:
        validated = validate_cxas_token(forwarded_auth.credentials)
        token_type = validated.claims.get("type")
        if not is_route_allowed(called_method, called_path, token_type):
            logger.warning(
                f"Forbidden access to {called_method} {called_path} with type '{token_type}' in forwarded_auth")
            raise HTTPException(
                status_code=403,
                detail="Forbidden: Route not allowed for forwarded authentication context type"
            )
        return validated

    # 2. Check for standard Authorization: Bearer <Token>
    if auth and auth.credentials:
        try:
            return validate_token_by_issuer(auth.credentials)
        except HTTPException as auth_err:
            if is_running_locally():
                logger.info(f"Local environment: ignoring invalid token '{auth.credentials}' and falling back to mock user token")
                return ValidatedToken.get_mock_token()
            raise auth_err

    # 3. Local Development Bypass: fallback to mock user token when running locally without auth header
    if is_running_locally():
        logger.info("Local environment: falling back to mock user token")
        return ValidatedToken.get_mock_token()

    raise HTTPException(status_code=401, detail="Unauthorized")


async def verify_eventarc_oidc_token(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    # Extract from request headers if dependency injection header is missing
    auth_header = authorization
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.error("Missing or invalid Authorization header in Eventarc invocation.")
        raise HTTPException(status_code=401, detail="Unauthorized Eventarc invocation.")
    
    token = auth_header.split("Bearer ")[1]
    try:
        project_id = get_project_id()
        expected_sa = f"banking-eventarc-sa@{project_id}.iam.gserviceaccount.com"
        # Verify the OIDC token signature and integrity via Google's public keys (audience checked manually below)
        id_info = id_token.verify_oauth2_token(token, requests.Request(), audience=None)
        
        # Manually validate the token audience belongs to your service endpoint prefix
        audience = id_info.get("aud", "")
        if not audience.startswith("https://banking-service-"):
            logger.error(f"Untrusted token audience: {audience}")
            raise HTTPException(status_code=403, detail="Untrusted OIDC token audience.")

        if id_info.get("email") != expected_sa:
            logger.error(f"Untrusted service account email: {id_info.get('email')}")
            raise HTTPException(status_code=403, detail="Untrusted Eventarc service account.")
        return id_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OIDC token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid OIDC token.")
