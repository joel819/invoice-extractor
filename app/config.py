"""Settings from environment variables / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "invoice-extractor"
    data_dir: Path = Path("./data")
    database_url: str = ""  # defaults to sqlite in data_dir
    seed_on_startup: bool = True
    max_upload_mb: int = 10
    max_pages: int = 20

    # LLM (Groq free tier via the OpenAI-compatible API)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 45.0
    llm_repair_attempts: int = 1  # re-ask the model once, with the validation errors, if its JSON is invalid

    # Validation
    low_confidence_threshold: float = 0.7  # fields below this are listed in low_confidence_fields
    money_tolerance: str = "0.02"  # rounding tolerance for arithmetic checks

    @property
    def demo_mode(self) -> bool:
        return not self.groq_api_key

    @property
    def sqlite_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
