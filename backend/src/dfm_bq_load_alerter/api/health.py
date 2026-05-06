import logging
import time
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from dfm_bq_load_alerter.db.session import sessionmaker_factory
from dfm_bq_load_alerter.settings import settings

router = APIRouter()
log = logging.getLogger(__name__)

_DB_PROBE_TTL_SECONDS = 30
_db_probe_cache: dict[str, Any] = {"ok": False, "checked_at": 0.0, "error": None}


async def _probe_database() -> tuple[bool, str | None]:
    try:
        sm = sessionmaker_factory()
    except RuntimeError as exc:
        return False, str(exc)
    try:
        async with sm() as session:
            await session.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 — health probe must not propagate
        return False, f"{type(exc).__name__}: {exc}"


async def _check_db_with_cache() -> tuple[bool, str | None]:
    now = time.monotonic()
    if now - _db_probe_cache["checked_at"] < _DB_PROBE_TTL_SECONDS:
        return _db_probe_cache["ok"], _db_probe_cache["error"]
    ok, err = await _probe_database()
    _db_probe_cache["ok"] = ok
    _db_probe_cache["error"] = err
    _db_probe_cache["checked_at"] = now
    if not ok:
        log.warning("DB healthcheck failed: %s", err)
    return ok, err


@router.get("/healthz")
async def healthz() -> JSONResponse:
    if not settings.postgres_dsn:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "db": "not-configured"},
        )
    ok, err = await _check_db_with_cache()
    if ok:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "db": "ok"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "degraded", "db": "fail", "error": err},
    )
