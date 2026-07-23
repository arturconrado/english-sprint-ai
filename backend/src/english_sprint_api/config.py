from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = Field(
        default="postgresql://english_sprint:english_sprint@localhost:5432/english_sprint",
        min_length=1,
    )
    redis_url: str = Field(default="redis://localhost:6379/0", min_length=1)
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
