import os
import sys
import logging
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine.url import make_url

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Append the parent banking-service directory to sys.path so python resolves local package imports correctly
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from utils.database import Base, DATABASE_URL  # noqa: E402
# Import all database models to ensure they register on Base.metadata for autogenerate detection
import models.credit_card  # noqa: E402, F401
import models.support  # noqa: E402, F401
import models.settings  # noqa: E402, F401

# Set target metadata for alembic schema scanning
target_metadata = Base.metadata

# Inject the dynamic DATABASE_URL connection string directly into the alembic configuration
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Configure masked database URL for logging safety
logger = logging.getLogger("alembic.runtime.environment")
try:
    parsed_url = make_url(DATABASE_URL)
    masked_url = parsed_url._replace(password="********").render_as_string(hide_password=False)
except Exception:
    masked_url = "Redacted Connection String"

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    logger.info(f"Running offline migrations against: {masked_url}")
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    logger.info(f"Running online migrations against: {masked_url}")
    from utils.database import create_db_engine
    connectable = create_db_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # Detect if we are deploying against PostgreSQL to prevent horizontal scaling lock contention
        is_postgres = connection.dialect.name == "postgresql"

        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            if is_postgres:
                logger.info("Acquiring transactional advisory migration lock (ID: 592837410)...")
                connection.execute(sa.text("SELECT pg_advisory_xact_lock(592837410);"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
