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
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///banking.db")
db_password = os.getenv("DB_PASSWORD")
if db_password and "@" in DATABASE_URL:
    parts = DATABASE_URL.split("@", 1)
    user_part = parts[0].split("://", 1)[1]
    if ":" not in user_part:
        DATABASE_URL = parts[0] + ":" + db_password + "@" + parts[1]


def get_iam_connection(url_str):
    import google.auth
    import google.auth.transport.requests
    import psycopg2
    from sqlalchemy.engine import make_url

    url = make_url(url_str)
    credentials, project = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/sqlservice.login",
            "https://www.googleapis.com/auth/cloud-platform",
        ]
    )
    request = google.auth.transport.requests.Request()
    logger.info(f"Refreshing GCP credentials of type: {type(credentials)}")
    credentials.refresh(request)
    logger.info(f"Credentials refresh completed. Token present: {credentials.token is not None}")
    if credentials.token:
        logger.info(f"Token length: {len(credentials.token)}")
    
    # If host is in query (Unix socket path) or host is None, check query host
    host_val = url.host or url.query.get("host")
    
    conn_params = {
        "host": host_val,
        "database": url.database,
        "user": url.username,
        "password": credentials.token,
    }
    
    # Only set port and sslmode if we are using TCP/IP (i.e. host is not a unix socket path starting with /)
    if host_val and not host_val.startswith("/"):
        conn_params["port"] = url.port or 5432
        if url.query.get("sslmode"):
            conn_params["sslmode"] = url.query["sslmode"]
        else:
            conn_params["sslmode"] = "require"
        
    return psycopg2.connect(**conn_params)

def create_db_engine(url_str=DATABASE_URL, **kwargs):
    connect_args = {}
    engine_args = kwargs.copy()
    
    if url_str.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif url_str.startswith("postgresql"):
        if "pool_size" not in engine_args and "poolclass" not in engine_args:
            engine_args["pool_size"] = 10
            engine_args["max_overflow"] = 20
            engine_args["pool_recycle"] = 900
            engine_args["pool_pre_ping"] = True
            
        if os.getenv("DB_IAM_AUTH") == "true":
            logger.info("Using GCP IAM authentication for Cloud SQL PostgreSQL connection.")
            engine_args["creator"] = lambda: get_iam_connection(url_str)
            
    logger.info(f"Creating database engine for connection: {url_str.split('@')[-1]}")
    return create_engine(url_str, connect_args=connect_args, **engine_args)

engine = create_db_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI Dependency: Yields a scoped database session and closes it on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
