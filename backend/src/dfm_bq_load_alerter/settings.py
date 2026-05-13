from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DFM_ALERT_", case_sensitive=False)

    static_dir: Path = Field(
        default=Path("/app/static"),
        description="React build output directory served as SPA root",
    )
    log_level: str = Field(default="INFO")
    environment: Literal["development", "staging", "production"] = Field(default="production")

    postgres_dsn: str = Field(default="")
    postgres_session_timezone: str = Field(default="Asia/Seoul")

    bq_project_id: str = Field(default="")
    bq_dataset_list: str = Field(default="")
    bq_credentials_path: Path = Field(default=Path("/var/secrets/bq-sa/key.json"))

    # OIDC (Keycloak)
    oidc_issuer: str = Field(default="")
    oidc_client_id: str = Field(default="")
    oidc_client_secret: str = Field(default="")
    oidc_redirect_uri: str = Field(
        default="",
        description="절대 URL. 빈 값이면 callback 시 request URL로 자동 산출.",
    )
    oidc_post_logout_redirect_uri: str = Field(default="")

    # Session cookie
    session_secret_key: str = Field(default="")
    session_max_age_seconds: int = Field(default=28800)

    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_addr: str = Field(default="")
    smtp_use_starttls: bool = Field(default=True)
    smtp_local_hostname: str = Field(default="")

    default_threshold_percent: float = Field(default=25.0)
    retention_days: int = Field(default=90)
    scheduler_timezone: str = Field(default="Asia/Seoul")
    scheduler_enabled: bool = Field(default=True)
    leader_election_enabled: bool = Field(default=True)
    leader_ping_seconds: int = Field(default=30, ge=5, le=300)
    misfire_grace_check_seconds: int = Field(default=120)
    misfire_grace_report_seconds: int = Field(default=600)
    condition_query_max_bytes: int = Field(default=104857600)
    bq_max_concurrency: int = Field(default=5, ge=1, le=64)
    teams_chunk_delay_seconds: float = Field(default=5.0, ge=0.0, le=60.0)

    @property
    def bq_datasets(self) -> list[str]:
        return [d.strip() for d in self.bq_dataset_list.split(",") if d.strip()]

    @model_validator(mode="after")
    def _require_oidc_and_session(self) -> "Settings":
        missing = [
            name
            for name, value in [
                ("DFM_ALERT_OIDC_ISSUER", self.oidc_issuer),
                ("DFM_ALERT_OIDC_CLIENT_ID", self.oidc_client_id),
                ("DFM_ALERT_OIDC_CLIENT_SECRET", self.oidc_client_secret),
                ("DFM_ALERT_SESSION_SECRET_KEY", self.session_secret_key),
            ]
            if not value
        ]
        if missing:
            raise ValueError(
                f"Required environment variables are missing: {', '.join(missing)}"
            )
        return self


settings = Settings()
