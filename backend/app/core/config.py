from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (coderev/) — .env and github-app.pem live here
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

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

    # LLM (OpenRouter compatible — uses OpenAI SDK)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "anthropic/claude-haiku-4-5"
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"
    LOCAL_LLM_URL: Optional[str] = None

    # Sandbox — isolated venv per test run (native Windows / Linux / macOS)
    SANDBOX_WORKSPACE_DIR: str = str(Path.home() / "coderev_sandboxes")
    SANDBOX_TIMEOUT_SECONDS: int = 120

    # Agent limits
    AGENT_MAX_RETRIES: int = 3
    AGENT_MAX_TOOL_CALLS: int = 50
    AGENT_TIMEOUT_SECONDS: int = 300

    def resolve_private_key_path(self) -> Path:
        """Resolve GitHub App PEM relative to project root when path is relative."""
        path = Path(self.GITHUB_APP_PRIVATE_KEY_PATH)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
