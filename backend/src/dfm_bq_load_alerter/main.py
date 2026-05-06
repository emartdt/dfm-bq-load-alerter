import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dfm_bq_load_alerter import __version__
from dfm_bq_load_alerter.api import alerts, checks, health, tables
from dfm_bq_load_alerter.db.session import dispose_engine
from dfm_bq_load_alerter.settings import settings

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await dispose_engine()


app = FastAPI(title="dfm-bq-load-alerter", version=__version__, lifespan=lifespan)

# Backend routers MUST be registered before any catch-all so SPA fallback
# does not intercept /api/*, /auth/*, /healthz, /assets/* requests (C2 guard).
app.include_router(health.router)
app.include_router(alerts.router, prefix="/api")  # legacy mock — deprecate in PR-5
app.include_router(tables.router)
app.include_router(checks.router)


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
