from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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
    realtime_enabled: bool = False
    realtime_provider: Literal["openai"] = "openai"
    openai_api_key: SecretStr | None = None
    openai_realtime_model: str = "gpt-realtime-2.1-mini"
    openai_realtime_voice: str = "marin"
    installation_hash_secret: SecretStr | None = None
    realtime_create_timeout_seconds: float = Field(default=15.0, gt=0, le=30)
    realtime_sideband_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    realtime_hangup_timeout_seconds: float = Field(default=5.0, gt=0, le=15)
    realtime_max_duration_seconds: int = Field(default=1800, ge=60, le=1800)
    realtime_redis_ttl_seconds: int = Field(default=2100, ge=1800, le=3600)
    realtime_rate_limit_per_hour: int = Field(default=10, ge=1, le=100)
    realtime_vad_threshold: float = Field(default=0.55, ge=0, le=1)
    realtime_vad_prefix_padding_ms: int = Field(default=300, ge=0, le=2000)
    realtime_vad_silence_duration_ms: int = Field(default=600, ge=100, le=5000)

    @property
    def realtime_configuration_valid(self) -> bool:
        if not self.realtime_enabled:
            return True
        return bool(
            self.openai_api_key
            and self.installation_hash_secret
            and self.openai_realtime_model
            and self.openai_realtime_voice
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
