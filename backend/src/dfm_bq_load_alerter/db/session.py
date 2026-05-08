from collections.abc import AsyncGenerator

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dfm_bq_load_alerter.settings import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    if not settings.postgres_dsn:
        raise RuntimeError(
            "DFM_ALERT_POSTGRES_DSN is not configured. Set it via env or chart values."
        )
    connect_args: dict[str, object] = {
        "server_settings": {"timezone": settings.postgres_session_timezone},
    }
    # 로컬 개발은 cloud-sql-auth-proxy(plain TCP) 경유. asyncpg 의 기본
    # ssl="prefer" 는 업그레이드 핸드셰이크를 시도하다 간헐적으로 끊어진다.
    # prod 는 Cloud SQL Connector / Private IP 가 SSL 을 알아서 처리하므로
    # development 에서만 명시적으로 SSL 을 끈다.
    if settings.environment == "development":
        connect_args["ssl"] = False
    return create_async_engine(
        settings.postgres_dsn,
        echo=False,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
        poolclass=NullPool if settings.environment == "development" else None,
    )


def session_factory() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def sessionmaker_factory() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            session_factory(), expire_on_commit=False, autoflush=False
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with sessionmaker_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def build_url_from_components(
    user: str, password: str, host: str, port: int, database: str
) -> str:
    return URL.create(
        drivername="postgresql+asyncpg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)
