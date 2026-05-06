from __future__ import annotations

from functools import lru_cache

from google.cloud import bigquery

from dfm_bq_load_alerter.settings import settings


@lru_cache(maxsize=1)
def get_client() -> bigquery.Client:
    """Return a process-singleton BigQuery client.

    GOOGLE_APPLICATION_CREDENTIALS env (set from chart at runtime) provides
    the SA key path. The bigquery.Client picks it up automatically.
    """
    if not settings.bq_project_id:
        raise RuntimeError(
            "DFM_ALERT_BQ_PROJECT_ID is not configured. "
            "Set the GCP project that hosts the monitored datasets."
        )
    return bigquery.Client(project=settings.bq_project_id)
