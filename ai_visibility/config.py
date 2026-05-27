"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Langfuse env vars are read by its own SDK
        protected_namespaces=(),
    )

    openai_api_key: str = ""  # Required for API calls; empty OK for tests/offline

    model_generator: str = "gpt-4.1-mini-2025-04-14"
    model_simulator: str = "gpt-4.1-mini-2025-04-14"
    model_judge: str = "gpt-4.1-mini-2025-04-14"

    temperature_generator: float = 0.7
    temperature_simulator: float = 0.3
    temperature_judge: float = 0.0

    seed: int = 42
    semaphore_limit: int = 5
    max_retries: int = 5

    cache_dir: str = "./.cache"
    cache_ttl_seconds: int = 86400  # 24h

    database_url: str = "postgresql://app:dev@localhost:5432/ai_visibility"


settings = Settings()
