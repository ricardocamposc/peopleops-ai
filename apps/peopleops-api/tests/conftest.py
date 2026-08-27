from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from alembic import command
from peopleops_api.config import Settings
from peopleops_api.db import create_session_factory, database_url


@pytest.fixture(scope="session", autouse=True)
def apply_peopleops_migrations() -> None:
    """Apply the Slice 01 schema to the real PostgreSQL test database."""
    settings = Settings(
        PEOPLEOPS_DATABASE_HOST="localhost",
        PEOPLEOPS_DATABASE_PORT=5436,
        PEOPLEOPS_DATABASE_NAME="peopleops",
        PEOPLEOPS_DATABASE_USER="peopleops_app",
        PEOPLEOPS_DATABASE_PASSWORD="peopleops_local_placeholder",
    )
    api_root = Path(__file__).parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url(settings).replace("%", "%%"))
    command.upgrade(config, "head")


@pytest.fixture()
def db_session():
    """Provide a transactional session against the real PostgreSQL test database."""
    settings = Settings(
        PEOPLEOPS_DATABASE_HOST="localhost",
        PEOPLEOPS_DATABASE_PORT=5436,
        PEOPLEOPS_DATABASE_NAME="peopleops",
        PEOPLEOPS_DATABASE_USER="peopleops_app",
        PEOPLEOPS_DATABASE_PASSWORD="peopleops_local_placeholder",
    )
    factory = create_session_factory(settings)
    session = factory()
    try:
        session.execute(text("SELECT 1"))
    except OperationalError:
        session.close()
        pytest.skip("local PostgreSQL is not available")
    yield session
    session.rollback()
    session.close()
