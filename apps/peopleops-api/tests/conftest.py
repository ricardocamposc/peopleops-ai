from urllib.parse import quote
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from peopleops_api.config import Settings
from peopleops_api.db import Base, database_url
from peopleops_api import models  # noqa: F401


def _test_settings() -> Settings:
    return Settings(
        PEOPLEOPS_DATABASE_HOST="localhost",
        PEOPLEOPS_DATABASE_PORT=5436,
        PEOPLEOPS_DATABASE_NAME="peopleops",
        PEOPLEOPS_DATABASE_USER="peopleops_app",
        PEOPLEOPS_DATABASE_PASSWORD="peopleops_local_placeholder",
    )


def _schema_database_url(settings: Settings, schema: str) -> str:
    options = quote(f"-csearch_path={schema},public", safe="")
    return f"{database_url(settings)}?options={options}"


@pytest.fixture(scope="session")
def test_schema():
    """Create a disposable PostgreSQL schema isolated from development/evaluation data."""
    settings = _test_settings()
    schema = f"pytest_{uuid4().hex}"
    engine = create_engine(database_url(settings), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        yield schema
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def apply_peopleops_schema(test_schema: str) -> None:
    """Create all test tables only inside the disposable test schema."""
    settings = _test_settings()
    engine = create_engine(_schema_database_url(settings, test_schema), pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text(f'SET search_path TO "{test_schema}", public'))
        isolated_connection = connection.execution_options(
            schema_translate_map={None: test_schema}
        )
        Base.metadata.create_all(isolated_connection)
    engine.dispose()


@pytest.fixture()
def db_session(test_schema: str, apply_peopleops_schema):
    """Provide a transactional session inside the disposable test schema."""
    settings = _test_settings()
    engine = create_engine(_schema_database_url(settings, test_schema), pool_pre_ping=True)
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        session.execute(text("SELECT 1"))
    except OperationalError:
        session.close()
        pytest.skip("local PostgreSQL is not available")
    yield session
    session.rollback()
    session.close()
    engine.dispose()
