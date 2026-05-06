from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DFM_ALERT_", case_sensitive=False)

    static_dir: Path = Field(
        default=Path("/app/static"),
        description="React build output directory served as SPA root",
    )
    log_level: str = Field(default="INFO")


settings = Settings()
