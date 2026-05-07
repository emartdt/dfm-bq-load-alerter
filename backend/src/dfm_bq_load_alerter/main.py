import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dfm_bq_load_alerter import __version__
from dfm_bq_load_alerter.api import (
    alerts,
    checks,
    groups,
    health,
    history,
    policy,
    recipients,
    tables,
    webhooks,
)
from dfm_bq_load_alerter.db.session import dispose_engine, session_factory
from dfm_bq_load_alerter.scheduler import Leader, build_scheduler, register_jobs
from dfm_bq_load_alerter.settings import settings

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    leader: Leader | None = None
    scheduler: AsyncIOScheduler | None = None
    heartbeat_task: asyncio.Task[None] | None = None

    if settings.scheduler_enabled and settings.postgres_dsn:
        leader = Leader(session_factory(), ping_seconds=settings.leader_ping_seconds)

        async def on_acquired() -> None:
            nonlocal scheduler
            if scheduler is None or not scheduler.running:
                scheduler = build_scheduler()
                register_jobs(scheduler)
                scheduler.start()
                log.info("scheduler started (leader)")

        async def on_lost() -> None:
            nonlocal scheduler
            if scheduler is not None and scheduler.running:
                scheduler.shutdown(wait=False)
                log.warning("scheduler shutdown (lost leader)")
            scheduler = None

        if await leader.try_acquire():
            await on_acquired()

        heartbeat_task = asyncio.create_task(
            leader.run_forever(on_acquired=on_acquired, on_lost=on_lost),
            name="leader-heartbeat",
        )

    try:
        yield
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await heartbeat_task
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)
        if leader is not None:
            await leader.release()
        await dispose_engine()


app = FastAPI(title="dfm-bq-load-alerter", version=__version__, lifespan=lifespan)

# Backend routers MUST be registered before any catch-all so SPA fallback
# does not intercept /api/*, /auth/*, /healthz, /assets/* requests (C2 guard).
app.include_router(health.router)
app.include_router(alerts.router, prefix="/api")  # legacy mock — deprecate in PR-5
app.include_router(tables.router)
app.include_router(recipients.router)
app.include_router(webhooks.router)
app.include_router(groups.router)
app.include_router(checks.router)
app.include_router(history.router)
app.include_router(policy.router)


@app.get("/api/version")
def version() -> dict[str, str]:
    return {"version": __version__}


_BACKEND_PREFIXES: tuple[str, ...] = ("api/", "auth/", "healthz", "assets/")

if settings.static_dir.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=settings.static_dir / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith(_BACKEND_PREFIXES):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return FileResponse(settings.static_dir / "index.html")
