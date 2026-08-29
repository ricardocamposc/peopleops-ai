from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_name: str = "reference-mcp-server"
    synthetic_hris_database_host: str = Field(
        default="synthetic-hris-db", alias="SYNTHETIC_HRIS_DATABASE_HOST"
    )
    synthetic_hris_database_port: int = Field(default=5432, alias="SYNTHETIC_HRIS_DATABASE_PORT")
    synthetic_hris_database_name: str = Field(
        default="synthetic_hris", alias="SYNTHETIC_HRIS_DATABASE_NAME"
    )
    synthetic_hris_database_user: str = Field(
        default="synthetic_hris_app", alias="SYNTHETIC_HRIS_DATABASE_USER"
    )
    synthetic_hris_database_password: str = Field(
        default="", alias="SYNTHETIC_HRIS_DATABASE_PASSWORD"
    )
    query_timeout_seconds: float = Field(default=5.0, gt=0, le=60, alias="QUERY_TIMEOUT_SECONDS")
    max_result_rows: int = Field(default=1000, ge=1, le=10000, alias="MAX_RESULT_ROWS")
    max_result_bytes: int = Field(
        default=1_048_576, ge=1024, le=10_485_760, alias="MAX_RESULT_BYTES"
    )
    mcp_audit_enabled: bool = Field(default=True, alias="MCP_AUDIT_ENABLED")
    mcp_audit_schema: str = Field(default="mcp_audit", alias="MCP_AUDIT_SCHEMA")


@lru_cache
def get_settings() -> Settings:
    return Settings()
