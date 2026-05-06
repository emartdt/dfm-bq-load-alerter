from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["alerts"])


class Alert(BaseModel):
    id: str
    severity: str
    message: str
    occurred_at: datetime


@router.get("/alerts", response_model=list[Alert])
def list_alerts() -> list[Alert]:
    # MVP: 실제 BigQuery 연동 전까지 mock 데이터 반환.
    now = datetime.now(timezone.utc)
    return [
        Alert(id="mock-1", severity="info", message="아직 실제 알림 소스가 연결되지 않았습니다.", occurred_at=now),
    ]
