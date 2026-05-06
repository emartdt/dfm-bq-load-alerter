import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dfm_bq_load_alerter import __version__
from dfm_bq_load_alerter.api import alerts, health
from dfm_bq_load_alerter.settings import settings

logging.basicConfig(level=settings.log_level)

app = FastAPI(title="dfm-bq-load-alerter", version=__version__)

app.include_router(health.router)
app.include_router(alerts.router, prefix="/api")


@app.get("/api/version")
def version() -> dict[str, str]:
    return {"version": __version__}


if settings.static_dir.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=settings.static_dir / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        return FileResponse(settings.static_dir / "index.html")
