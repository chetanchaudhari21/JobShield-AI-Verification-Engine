import logging
import os
import sys
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url
from alembic import context

# Ensure backend directory is in sys.path so app.* modules are discoverable
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, ".."))
workspace_dir = os.path.abspath(os.path.join(backend_dir, ".."))

for path in [backend_dir, workspace_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from app.core.config import settings
from app.db.base import Base
# Import all models to register with Base.metadata
import app.models  # noqa: F401

logger = logging.getLogger("alembic.env")

config = getattr(context, "config", None)

if config is not None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_target_url() -> str:
    """
    Determine target DB URL.
    1. CLI / programmatic argument (-x url=...) if explicitly provided.
    2. settings.DATABASE_URL loaded from Pydantic settings and .env.
    
    IMPORTANT: The placeholder 'sqlalchemy.url' in alembic.ini is ignored and
    will NEVER override settings.DATABASE_URL.
    """
    if hasattr(context, "get_x_argument"):
        try:
            x_args = context.get_x_argument(as_dictionary=True)
            if "url" in x_args and x_args["url"]:
                return x_args["url"]
        except Exception:
            pass

    # Always use settings.DATABASE_URL from Pydantic settings
    return settings.DATABASE_URL


def get_sanitized_target_url(url: str = None) -> str:
    """
    Returns the database URL with any password safely masked as '***'.
    Ensures Alembic never logs or prints credentials.
    """
    target = url or get_target_url()
    try:
        url_obj = make_url(target)
        return url_obj.render_as_string(hide_password=True)
    except Exception:
        return "<sanitized database url>"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_target_url()
    logger.info("Running offline migrations targeting: %s", get_sanitized_target_url(url))

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = get_target_url()
    logger.info("Running online migrations targeting: %s", get_sanitized_target_url(url))

    connect_args = {}
    if "sqlite" in url:
        connect_args["check_same_thread"] = False
    elif "psycopg" in url:
        connect_args["connect_timeout"] = 5

    connectable = create_engine(
        url,
        connect_args=connect_args,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


try:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
except NameError:
    # Proxy not established; env.py was imported as a Python module for configuration inspection/testing
    pass
