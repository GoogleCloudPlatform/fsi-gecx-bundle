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

import logging
import os
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi

from routers.application import router as application_router
from routers.cxas_authentication import router as cxas_auth_router
from routers.ccai_authentication import router as ccai_auth_router
from routers.artifact import router as artifact_router
from routers.profile import router as profile_router
from routers.internal import router as internal_router
from routers.notification import router as notification_router
from routers.health import router as health_router
from routers.search import router as search_router
from routers.secure_messaging import router as secure_messaging_router
from routers.underwriting import router as underwriting_router
from routers.credit_card import router as credit_card_router
from routers.support import router as support_router
from routers.settings import router as settings_router
from models.authentication import ValidatedToken
from utils.auth import get_current_user
from routers.locator import router as locator_router
from routers.accounts import router as accounts_router, alias_router as accounts_alias_router
from routers.fdx import router as fdx_router

# Import and register FastMCP tools and ASGI app from the isolated mcp router module
from routers.mcp import mcp_app
from routers.voice_bidi import router as voice_bidi_router

import firebase_admin
from contextlib import asynccontextmanager

# Initialize Firebase Admin SDK using Application Default Credentials (ADC)
try:
    firebase_admin.initialize_app()
    logging.info("Firebase Admin SDK initialized successfully.")
except ValueError:
    # Firebase Admin SDK is already initialized (this can happen during reloads or tests)
    pass
except Exception as e:
    logging.error(f"Failed to initialize Firebase Admin SDK: {e}")


import asyncio

async def run_db_seeding():
    logging.info("Starting background database verification and seeding...")
    try:
        from utils.database import SessionLocal
        from services.seeding_service import perform_algorithmic_seeding
        db = SessionLocal()
        try:
            # Execute seeding in thread pool to prevent blocking main event loop
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, perform_algorithmic_seeding, db)
            logging.info("Background database seeding completed successfully.")
        finally:
            db.close()
    except Exception as e:
        logging.error(f"Error during background database seeding: {e}")


@asynccontextmanager
async def combined_lifespan(app_inst: FastAPI):
    import sys
    if "pytest" not in sys.modules:
        logging.info("Scheduling background database seeding task on lifespan startup...")
        asyncio.create_task(run_db_seeding())
    else:
        logging.info("Test environment detected. Skipping background database seeding task.")
    async with mcp_app.lifespan(app_inst):
        yield


app = FastAPI(
    lifespan=combined_lifespan,
    title="Banking Service API",
    description=(
        "Banking Service API for managing interactions."
    ),
    version="0.0.1",
    root_path=os.getenv("ROOT_PATH", ""),
    servers=[
        {
            "url": "http://localhost:8080"
        },
        # {
        #     "url": "https://banking-service-362868133740.us-central1.run.app"
        # }
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
)

app.include_router(application_router)
app.include_router(artifact_router)
app.include_router(ccai_auth_router)
app.include_router(cxas_auth_router)
app.include_router(internal_router)
app.include_router(locator_router)
app.include_router(notification_router)
app.include_router(profile_router)
app.include_router(health_router)
app.include_router(search_router)
app.include_router(secure_messaging_router)
app.include_router(underwriting_router)
app.include_router(credit_card_router)
app.include_router(support_router)
app.include_router(settings_router)
app.include_router(voice_bidi_router)
app.include_router(accounts_router)
app.include_router(accounts_alias_router)
app.include_router(fdx_router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    for path in openapi_schema.get("paths", {}).values():
        for operation in path.values():
            if isinstance(operation, dict):
                # Check if this operation has HTTPForwardedBearer security requirement
                has_forwarded_auth = False
                for sec_req in operation.get("security", []):
                    if "HTTPForwardedBearer" in sec_req:
                        has_forwarded_auth = True
                        break

                if has_forwarded_auth:
                    if "parameters" not in operation:
                        operation["parameters"] = []

                    # See if x-forwarded-user-context already exists
                    has_param = False
                    for param in operation["parameters"]:
                        if (
                                isinstance(param, dict) and
                                isinstance(param.get("name"), str) and
                                param.get("name").lower() == "x-forwarded-user-context" and
                                param.get("in") == "header"
                        ):
                            param["x-ces-session-context"] = "$context.variables.access_token"
                            has_param = True
                            break

                    if not has_param:
                        operation["parameters"].append({
                            "name": "X-Forwarded-User-Context",
                            "in": "header",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "nullable": True,
                                "title": "X-Forwarded-User-Context"
                            },
                            "x-ces-session-context": "$context.variables.access_token"
                        })

    openapi_schema["servers"] = app.servers

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/user", summary="Get current user", description="Get current user from IAP.", tags=["user"])
async def get_user(user: ValidatedToken = Depends(get_current_user)):
    return user


# Mount FastMCP directly onto the core application
app.mount("/mcp", mcp_app)

# Alias combined_app to app so any startup script referencing main:combined_app executes the full application cleanly
combined_app = app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:combined_app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=True,
    )
