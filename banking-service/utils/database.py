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
import sys
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url, Engine
from sqlalchemy.orm import declarative_base, sessionmaker

import uuid as _uuid
from sqlalchemy.types import TypeDecorator, Uuid

logger = logging.getLogger(__name__)

class StringComparableUUID(_uuid.UUID):
    def __eq__(self, other):
        if isinstance(other, str):
            try:
                return super().__eq__(_uuid.UUID(other))
            except ValueError:
                return str(self) == other
        return super().__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return super().__hash__()


def generate_uuid():
    return StringComparableUUID(str(_uuid.uuid4()))


class UniversalUUID(TypeDecorator):
    """Platform-independent UUID type that accepts both strings and uuid.UUID objects."""
    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return _uuid.UUID(value)
            except ValueError:
                return value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return StringComparableUUID(str(value))
        if isinstance(value, str):
            try:
                return StringComparableUUID(value)
            except ValueError:
                return value
        return value


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
            conn_params["sslmode"] = "verify-full"
        
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
            
    sanitized_url = make_url(url_str).render_as_string(hide_password=True)
    logger.info(f"Creating database engine for connection: {sanitized_url}")
    new_engine = create_engine(url_str, connect_args=connect_args, **engine_args)

    return new_engine


@event.listens_for(Engine, "connect")
def attach_sqlite_schemas(dbapi_connection, connection_record):
    if "sqlite" not in type(dbapi_connection).__module__.lower():
        return
    if hasattr(dbapi_connection, "cursor"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT 1 FROM identity.sqlite_master LIMIT 1;")
            cursor.execute("SELECT 1 FROM origination.sqlite_master LIMIT 1;")
            cursor.execute("SELECT 1 FROM audit.sqlite_master LIMIT 1;")
            cursor.execute("SELECT 1 FROM admin.sqlite_master LIMIT 1;")
            cursor.close()
            return
        except Exception:
            pass

        try:
            cursor.execute("PRAGMA database_list;")
            rows = cursor.fetchall()
            main_file = ""
            for row in rows:
                if row[1] == "main":
                    main_file = row[2] if len(row) > 2 and row[2] else ""
                    break

            if not main_file:
                stmts = [
                    "ATTACH DATABASE 'file:identity_mem?mode=memory&cache=shared' AS identity;",
                    "ATTACH DATABASE 'file:kyc_mem?mode=memory&cache=shared' AS kyc;",
                    "ATTACH DATABASE 'file:ledger_mem?mode=memory&cache=shared' AS ledger;",
                    "ATTACH DATABASE 'file:cards_mem?mode=memory&cache=shared' AS cards;",
                    "ATTACH DATABASE 'file:operations_mem?mode=memory&cache=shared' AS operations;",
                    "ATTACH DATABASE 'file:origination_mem?mode=memory&cache=shared' AS origination;",
                    "ATTACH DATABASE 'file:audit_mem?mode=memory&cache=shared' AS audit;",
                    "ATTACH DATABASE 'file:admin_mem?mode=memory&cache=shared' AS admin;",
                    "ATTACH DATABASE 'file:catalog_mem?mode=memory&cache=shared' AS catalog;",
                    "ATTACH DATABASE 'file:ref_data_mem?mode=memory&cache=shared' AS ref_data;",
                ]
            else:
                base_prefix = main_file.rsplit(".", 1)[0] if "." in main_file else main_file
                if base_prefix.endswith("banking"):
                    base_prefix = ""
                else:
                    base_prefix = base_prefix + "_"
                stmts = [
                    f"ATTACH DATABASE '{base_prefix}identity.db' AS identity;",
                    f"ATTACH DATABASE '{base_prefix}kyc.db' AS kyc;",
                    f"ATTACH DATABASE '{base_prefix}ledger.db' AS ledger;",
                    f"ATTACH DATABASE '{base_prefix}cards.db' AS cards;",
                    f"ATTACH DATABASE '{base_prefix}operations.db' AS operations;",
                    f"ATTACH DATABASE '{base_prefix}origination.db' AS origination;",
                    f"ATTACH DATABASE '{base_prefix}audit.db' AS audit;",
                    f"ATTACH DATABASE '{base_prefix}admin.db' AS admin;",
                    f"ATTACH DATABASE '{base_prefix}catalog.db' AS catalog;",
                    f"ATTACH DATABASE '{base_prefix}ref_data.db' AS ref_data;",
                ]

            for stmt in stmts:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            cursor.close()


LEDGER_DATABASE_URL = os.getenv("LEDGER_DATABASE_URL", DATABASE_URL)
KYC_DATABASE_URL = os.getenv("KYC_DATABASE_URL", DATABASE_URL)

ledger_pool = create_db_engine(LEDGER_DATABASE_URL)
ledger_pool._rbac_role = "ledger_service_role"

kyc_pool = create_db_engine(KYC_DATABASE_URL)
kyc_pool._rbac_role = "kyc_service_role"

engine = ledger_pool

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ledger_pool)
KycSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=kyc_pool)
Base = declarative_base()


@event.listens_for(Engine, "before_cursor_execute")
def enforce_least_privilege_rbac(conn, cursor, statement, parameters, context, executemany):
    if conn.info.get("_ignore_rbac") or getattr(conn.engine, "_ignore_rbac", False):
        return
    role = getattr(conn.engine, "_rbac_role", None)
    if role in ("ledger_service_role", "kyc_service_role"):
        stmt_upper = statement.strip().upper()
        if any(stmt_upper.startswith(cmd) for cmd in ("UPDATE", "DELETE", "TRUNCATE")):
            if "ACCOUNT_LEDGER" in stmt_upper or "LEDGER.ACCOUNT_LEDGER" in stmt_upper:
                import sqlalchemy.exc
                raise sqlalchemy.exc.ProgrammingError(
                    "permission denied for table account_ledger (SQLSTATE 42501): account_ledger is immutable append-only",
                    params=parameters,
                    orig=Exception("SQLSTATE 42501")
                )
    if role == "ledger_service_role":
        stmt_upper = statement.strip().upper()
        if any(stmt_upper.startswith(cmd) for cmd in ("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")):
            if "KYC_RECORDS" in stmt_upper or "KYC." in stmt_upper:
                import sqlalchemy.exc
                raise sqlalchemy.exc.ProgrammingError(
                    "permission denied for schema kyc (SQLSTATE 42501)",
                    params=parameters,
                    orig=Exception("SQLSTATE 42501")
                )


def get_db():
    """FastAPI Dependency: Yields a scoped ledger database session and closes it on completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_kyc_db():
    """FastAPI Dependency: Yields a scoped KYC database session authenticated under kyc_service_role."""
    db = KycSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import models.identity  # noqa: F401
    import models.origination  # noqa: F401
    import models.audit  # noqa: F401
    import models.credit_card  # noqa: F401
    import models.support  # noqa: F401
    import models.settings  # noqa: F401
    import models.kyc  # noqa: F401
    import models.reference  # noqa: F401
    try:
        Base.metadata.create_all(bind=ledger_pool)
        Base.metadata.create_all(bind=kyc_pool)
    except Exception as e:
        logger.warning(f"Could not auto-initialize tables: {e}")


if not any("alembic" in arg for arg in sys.argv) and os.getenv("DISABLE_INIT_DB") != "true":
    init_db()
