from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "development"
    SECRET_KEY: str = "change-me"
    FRONTEND_URL: str = "http://localhost:3000"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://coderev:coderev@localhost:5432/coderev"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # GitHub App
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY_PATH: str = "./github-app.pem"
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    # LLM
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    LOCAL_LLM_URL: Optional[str] = None

    # Sandbox
    SANDBOX_DOCKER_HOST: str = "unix:///var/run/docker.sock"
    SANDBOX_WORKSPACE_DIR: str = "/tmp/coderev_sandboxes"
    SANDBOX_CPU_QUOTA: int = 50000
    SANDBOX_MEM_LIMIT: str = "512m"
    SANDBOX_TIMEOUT_SECONDS: int = 120

    # Agent limits
    AGENT_MAX_RETRIES: int = 3
    AGENT_MAX_TOOL_CALLS: int = 50
    AGENT_TIMEOUT_SECONDS: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
