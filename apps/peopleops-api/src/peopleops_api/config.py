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
    mcp_max_response_bytes: int = Field(
        default=1_048_576, ge=1024, le=10_485_760, alias="MCP_MAX_RESPONSE_BYTES"
    )
    openai_timeout_seconds: float = Field(
        default=30.0, gt=0, le=120, alias="OPENAI_TIMEOUT_SECONDS"
    )
    openai_max_retries: int = Field(default=0, ge=0, le=2, alias="OPENAI_MAX_RETRIES")
    openai_max_output_tokens: int = Field(
        default=4096, ge=256, le=16384, alias="OPENAI_MAX_OUTPUT_TOKENS"
    )
    max_question_length: int = Field(default=4000, ge=1, le=20000, alias="MAX_QUESTION_LENGTH")
    max_policy_top_k: int = Field(default=20, ge=1, le=50, alias="MAX_POLICY_TOP_K")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    hr_payroll_read_authorization_enabled: bool = Field(
        default=True, alias="HR_PAYROLL_READ_AUTHORIZATION_ENABLED"
    )
    hr_read_analysis_human_review_enabled: bool = Field(
        default=True, alias="HR_READ_ANALYSIS_HUMAN_REVIEW_ENABLED"
    )
    policy_storage_path: str = Field(default="./var/policies", alias="POLICY_STORAGE_PATH")
    policy_max_upload_bytes: int = Field(
        default=25 * 1024 * 1024, gt=0, alias="POLICY_MAX_UPLOAD_BYTES"
    )
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=1536, gt=0, alias="EMBEDDING_DIMENSION")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_project: str = Field(default="peopleops-ai", alias="LANGSMITH_PROJECT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
