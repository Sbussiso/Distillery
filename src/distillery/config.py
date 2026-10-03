"""Application settings (env-driven via pydantic-settings)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DISTILLERY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where Ollama lives.
    ollama_base_url: str = "http://localhost:11434"

    # Where distilled datasets are written on disk.
    datasets_dir: Path = Path("datasets")

    # Server bind.
    host: str = "127.0.0.1"
    port: int = 8000

    # Extra browser origins allowed to call the API cross-origin. Empty by
    # default: the UI is same-origin (built dist/ served by FastAPI, or the
    # Vite dev proxy), and a wildcard would let any website drive this local
    # server (start paid runs, delete datasets). JSON list in the env, e.g.
    # DISTILLERY_CORS_ORIGINS='["http://localhost:3000"]'.
    cors_origins: list[str] = []

    # Per-LLM-call safety caps (can be overridden per session).
    default_max_tokens: int = 2048
    default_timeout: float = 180.0

    @property
    def datasets_path(self) -> Path:
        p = Path(self.datasets_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()