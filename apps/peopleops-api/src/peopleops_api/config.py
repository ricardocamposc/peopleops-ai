from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_name: str = "peopleops-api"
    peopleops_database_host: str = Field(default="peopleops-db", alias="PEOPLEOPS_DATABASE_HOST")
    peopleops_database_port: int = Field(default=5432, alias="PEOPLEOPS_DATABASE_PORT")
    peopleops_database_name: str = Field(default="peopleops", alias="PEOPLEOPS_DATABASE_NAME")
    peopleops_database_user: str = Field(default="peopleops_app", alias="PEOPLEOPS_DATABASE_USER")
    peopleops_database_password: str = Field(default="", alias="PEOPLEOPS_DATABASE_PASSWORD")
    frontend_url: AnyHttpUrl = Field(default="http://localhost:3000", alias="FRONTEND_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
