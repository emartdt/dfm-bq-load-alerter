from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def test_asia_seoul_zoneinfo_available() -> None:
    """Dockerfile must install tzdata so zoneinfo can resolve Asia/Seoul (R10)."""
    tz = ZoneInfo("Asia/Seoul")
    assert tz is not None


def test_kst_offset_is_plus_9() -> None:
    """KST has no DST; offset is always +09:00."""
    sample = datetime(2026, 5, 6, 12, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    assert sample.utcoffset().total_seconds() == 9 * 3600


def test_utc_to_kst_date_boundary() -> None:
    """UTC 14:00 on day N → KST 23:00 (same day N); UTC 15:00 → KST 00:00 next day."""
    just_before_midnight = datetime(2026, 5, 6, 14, 0, tzinfo=UTC)
    kst = just_before_midnight.astimezone(ZoneInfo("Asia/Seoul"))
    assert kst.date() == datetime(2026, 5, 6).date()

    after_midnight = datetime(2026, 5, 6, 15, 0, tzinfo=UTC)
    kst2 = after_midnight.astimezone(ZoneInfo("Asia/Seoul"))
    assert kst2.date() == datetime(2026, 5, 7).date()
