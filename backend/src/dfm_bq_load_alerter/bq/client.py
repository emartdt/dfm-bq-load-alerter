from __future__ import annotations

from functools import lru_cache

from google.cloud import bigquery

from dfm_bq_load_alerter.settings import settings


@lru_cache(maxsize=16)
def get_client(project_id: str | None = None) -> bigquery.Client:
    """Return a (project-scoped) BigQuery client, cached per project.

    - `project_id` 가 주어지면 그 프로젝트로 클라이언트를 생성.
    - None 이면 `settings.bq_project_id` (env: DFM_ALERT_BQ_PROJECT_ID) 사용.

    GOOGLE_APPLICATION_CREDENTIALS 환경변수(차트에서 주입)가 SA 키 경로를
    제공하면 bigquery.Client 가 자동 인식한다.
    """
    project = project_id or settings.bq_project_id
    if not project:
        raise RuntimeError(
            "BigQuery project_id is not configured. "
            "Set tables.project_id or DFM_ALERT_BQ_PROJECT_ID."
        )
    return bigquery.Client(project=project)
