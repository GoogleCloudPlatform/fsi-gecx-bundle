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

# Resolve SQL database engine URL dynamically (SQLite local file by default, PostgreSQL for GCP)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///banking.db")

# SQLite needs 'check_same_thread=False' to allow multi-threaded asynchronous FastAPI routers
connect_args = {}
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
elif DATABASE_URL.startswith("postgresql"):
    # Optimize connection pool for serverless Cloud Run environment to prevent connection leaks/timeouts
    engine_args["pool_size"] = 10
    engine_args["max_overflow"] = 20
    engine_args["pool_recycle"] = 900
    engine_args["pool_pre_ping"] = True

logger.info(f"Initializing database engine with connection: {DATABASE_URL.split('@')[-1]}")
engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI Dependency: Yields a scoped database session and closes it on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
