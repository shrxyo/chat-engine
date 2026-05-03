from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at backend/src/app/config.py.
# Walk up three levels to reach backend/, then one more for the repo root.
# pydantic-settings accepts a list of paths and loads the first one found.
_BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/
_REPO_ROOT = _BACKEND_DIR.parent  # chat-engine/

_ENV_FILES = [
    _BACKEND_DIR / ".env",  # backend/.env  (local overrides)
    _REPO_ROOT / ".env",  # .env  (root, checked into repo convention)
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[str(p) for p in _ENV_FILES],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore Docker Compose vars (POSTGRES_USER etc.)
    )

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/chatengine"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # AI
    OPENAI_API_KEY: str = ""

    # Runtime
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
