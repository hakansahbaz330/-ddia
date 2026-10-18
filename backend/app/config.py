"""Ortam tabanlı yapılandırma. Sırlar yalnızca ortam değişkenlerinden / .env'den okunur."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_DIR / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{REPO_DIR / 'data' / 'football.sqlite'}"
    upload_dir: Path = REPO_DIR / "data" / "uploads"
    api_key: str = ""
    max_upload_mb: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
