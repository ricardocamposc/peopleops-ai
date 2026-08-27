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
    reference_mcp_server_url: AnyHttpUrl = Field(
        default="http://reference-mcp-server:8001", alias="REFERENCE_MCP_SERVER_URL"
    )
    mcp_timeout_seconds: float = Field(default=5.0, gt=0, alias="MCP_TIMEOUT_SECONDS")
    mcp_max_retries: int = Field(default=2, ge=0, le=5, alias="MCP_MAX_RETRIES")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    policy_storage_path: str = Field(default="./var/policies", alias="POLICY_STORAGE_PATH")
    policy_max_upload_bytes: int = Field(
        default=25 * 1024 * 1024, gt=0, alias="POLICY_MAX_UPLOAD_BYTES"
    )
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=1536, gt=0, alias="EMBEDDING_DIMENSION")


@lru_cache
def get_settings() -> Settings:
    return Settings()
