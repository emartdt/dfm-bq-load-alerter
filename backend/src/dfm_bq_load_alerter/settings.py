from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DFM_ALERT_", case_sensitive=False)

    static_dir: Path = Field(
        default=Path("/app/static"),
        description="React build output directory served as SPA root",
    )
    log_level: str = Field(default="INFO")
    environment: Literal["development", "staging", "production"] = Field(default="production")

    postgres_dsn: str = Field(
        default="",
        description="async SQLAlchemy DSN, e.g. postgresql+asyncpg://user:pass@host:5432/dfm_bq_load_alerter",
    )
    postgres_session_timezone: str = Field(default="Asia/Seoul")

    bq_project_id: str = Field(default="")
    bq_dataset_list: str = Field(
        default="",
        description="Comma-separated dataset names to monitor (e.g. 'sales,marketing')",
    )
    bq_credentials_path: Path = Field(
        default=Path("/var/secrets/bq-sa/key.json"),
        description="Service Account JSON path; mapped to GOOGLE_APPLICATION_CREDENTIALS",
    )

    oidc_issuer: str = Field(default="")
    oidc_client_id: str = Field(default="")
    oidc_client_secret: str = Field(default="")
    oidc_required_role: str = Field(default="dfm-alerter-admin")
    oidc_jwks_cache_ttl: int = Field(default=3600)
    oidc_jwt_leeway_seconds: int = Field(default=60)

    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_addr: str = Field(default="")
    smtp_use_starttls: bool = Field(default=True)

    teams_default_webhook_secret_ref: str = Field(default="")

    default_threshold_percent: float = Field(default=25.0)
    retention_days: int = Field(default=90)
    scheduler_timezone: str = Field(default="Asia/Seoul")
    condition_query_max_bytes: int = Field(default=104857600)

    bootstrap_token: str = Field(
        default="",
        description=(
            "PR-5 미머지 시점에만 사용하는 임시 admin 토큰. "
            "OIDC 설정이 정상 로드되면 무시."
        ),
    )

    @property
    def bq_datasets(self) -> list[str]:
        return [d.strip() for d in self.bq_dataset_list.split(",") if d.strip()]

    @property
    def is_oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id)


settings = Settings()
