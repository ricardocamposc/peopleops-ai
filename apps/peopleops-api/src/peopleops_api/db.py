from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from peopleops_api.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def database_url(settings: Settings) -> str:
    password = settings.peopleops_database_password
    return (
        f"postgresql+psycopg://{settings.peopleops_database_user}:{password}@"
        f"{settings.peopleops_database_host}:{settings.peopleops_database_port}/"
        f"{settings.peopleops_database_name}"
    )


def create_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    configured = settings or get_settings()
    engine = create_engine(database_url(configured), pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


SessionLocal = create_session_factory()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
