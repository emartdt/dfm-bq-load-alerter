from datetime import datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.notifier.template import (
    TemplateRow,
    build_email_html,
    build_email_subject,
    build_teams_card,
    build_teams_cards,
)

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 5, 6, 9, 0, tzinfo=KST)


def _row(status: str, **overrides) -> TemplateRow:
    base = dict(
        dataset="bw",
        table_name="PZEVENTID",
        expected_check_time=NOW,
        actual_check_time=NOW,
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=10.0,
        status=status,
        failure_reasons=[],
    )
    base.update(overrides)
    return TemplateRow(**base)


def test_subject_for_check_includes_fail_count() -> None:
    subject = build_email_subject(trigger_kind="check", fail_count=3, expected=NOW)
    assert "점검 실패 3건" in subject
    assert "2026-05-06" in subject


def test_subject_for_report_uses_report_label() -> None:
    subject = build_email_subject(trigger_kind="report", fail_count=0, expected=NOW)
    assert "일일 리포트" in subject


def test_email_html_renders_fail_section_only_when_fails_present() -> None:
    fail_row = _row("fail", failure_reasons=["row_count_zero"], today_row_count=0)
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[fail_row]
    )
    assert "FAIL (1)" in html
    assert "row_count_zero" in html
    assert "INSUFFICIENT" not in html


def test_email_html_escapes_dangerous_input() -> None:
    """HTML autoescape must neutralise <script> in dataset/table names."""
    bad = _row("fail", dataset="<script>alert(1)</script>", failure_reasons=["x"])
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[bad]
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_email_html_report_includes_ok_section() -> None:
    rows = [_row("ok"), _row("ok", table_name="OTHER")]
    _, html = build_email_html(
        trigger_kind="report", expected=NOW, actual=NOW, rows=rows
    )
    assert "OK (2)" in html


def test_email_html_report_renders_ok_rows_with_full_card_content() -> None:
    """리포트의 OK 행도 FAIL 카드와 동일한 풀 콘텐츠로 렌더되어야 한다.

    프로젝트·데이터셋·테이블·배치 시각·버퍼·이전/금일 row count + 유입 시각·
    증감(Δrows, Δ%) 모두 노출.
    """
    row = _row(
        "ok",
        project="bw-prj-001",
        dataset="bw",
        table_name="PZEVENTID",
        batch_time=time(7, 0),
        buffer_minutes=30,
        yesterday_row_count=1000,
        today_row_count=1050,
        delta_percent_vs_yesterday=5.0,
        yesterday_last_modified=datetime(2026, 5, 5, 7, 4, tzinfo=KST),
        today_last_modified=datetime(2026, 5, 6, 7, 6, tzinfo=KST),
    )
    _, html = build_email_html(
        trigger_kind="report", expected=NOW, actual=NOW, rows=[row]
    )
    # FQN
    assert "bw-prj-001" in html
    assert "PZEVENTID" in html
    # 배치 메타
    assert "예상 배치 시각" in html
    assert "07:00" in html
    assert "버퍼" in html
    assert "30분" in html
    # 이전/금일 row count + 유입 시각
    assert "이전 배치" in html
    assert "금일 배치" in html
    assert "1,000" in html
    assert "1,050" in html
    assert "2026-05-05 07:04:00" in html
    assert "2026-05-06 07:06:00" in html
    # 증감
    assert "+50" in html
    assert "+5.00%" in html


def test_email_html_check_trigger_omits_ok_section() -> None:
    rows = [_row("ok"), _row("fail", failure_reasons=["x"])]
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    assert "FAIL" in html
    assert "OK (" not in html


def _collect_types(items) -> set[str]:
    """Adaptive Card body 의 모든 노드 타입 집합 (Container 재귀 포함)."""
    found: set[str] = set()
    for item in items:
        found.add(item.get("type", ""))
        if item.get("type") == "Container":
            found |= _collect_types(item.get("items", []))
        if item.get("type") == "ColumnSet":
            for col in item.get("columns", []):
                found |= _collect_types(col.get("items", []))
    return found


def _headline(card: dict) -> dict:
    """제목(큰 TextBlock) 노드를 반환 — 트리거 라벨 다음에 오는 Large+Bolder 텍스트."""
    body = card["attachments"][0]["content"]["body"]
    return next(b for b in body if b.get("size") == "Large" and b.get("weight") == "Bolder")


def test_teams_card_structure_minimum() -> None:
    rows = [_row("fail", failure_reasons=["delta_exceeded"])]
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    assert card["type"] == "message"
    attachment = card["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    body = attachment["content"]["body"]
    body_kinds = _collect_types(body)
    assert "TextBlock" in body_kinds
    assert "Container" in body_kinds
    assert "ColumnSet" in body_kinds  # 이전/금일 비교 단


def test_teams_card_attention_color_when_fails() -> None:
    rows = [_row("fail", failure_reasons=["x"])]
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    assert _headline(card)["color"] == "Attention"


def test_teams_card_good_color_when_no_fails() -> None:
    rows = [_row("ok")]
    card = build_teams_card(
        trigger_kind="report", expected=NOW, actual=NOW, rows=rows
    )
    assert _headline(card)["color"] == "Good"


def test_email_html_includes_project_dataset_table_in_card() -> None:
    """프로젝트 prefix 가 카드 헤더에 노출되어야 한다."""
    row = _row(
        "fail",
        project="bw-prj-001",
        dataset="bw",
        table_name="PZEVENTID",
        failure_reasons=["delta_exceeded"],
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "bw-prj-001" in html
    assert "PZEVENTID" in html
    assert "bw" in html


def test_email_html_includes_batch_time_buffer_and_check_time() -> None:
    """예상 배치 시각 · 버퍼 N분 · 점검 시각 ... 메타 라인 검증."""
    row = _row(
        "fail",
        batch_time=time(7, 0),
        buffer_minutes=30,
        failure_reasons=["x"],
    )
    actual = datetime(2026, 5, 6, 7, 4, tzinfo=KST)
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=actual, rows=[row]
    )
    assert "예상 배치 시각" in html
    assert "07:00" in html
    assert "버퍼" in html
    assert "30분" in html
    assert "점검 시각" in html
    # 점검 시각은 actual_check_time(=row 의 actual_check_time) 기반.
    assert "2026-05-06 09:00:00" in html  # _row 의 actual_check_time(=NOW)
    # 옛 라벨이 남아있지 않아야 한다.
    assert "점검 윈도우 기준" not in html


def test_email_html_shows_delta_count_and_percent_with_sign() -> None:
    """오늘 - 어제 = -100, Δ% = -10.00% (부호 포함)."""
    row = _row(
        "fail",
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=-10.0,
        failure_reasons=["delta_exceeded"],
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "-100" in html
    assert "-10.00%" in html


def test_email_html_shows_previous_batch_load_time() -> None:
    yday = datetime(2026, 5, 5, 6, 58, tzinfo=KST)
    today = datetime(2026, 5, 6, 7, 4, tzinfo=KST)
    row = _row(
        "fail",
        yesterday_last_modified=yday,
        today_last_modified=today,
        failure_reasons=["delta_exceeded"],
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "2026-05-05 06:58:00" in html
    assert "2026-05-06 07:04:00" in html
    assert "이전 배치" in html
    assert "금일 배치" in html


def test_teams_card_fail_container_includes_project_batch_and_buffer() -> None:
    row = _row(
        "fail",
        project="bw-prj-001",
        batch_time=time(7, 0),
        buffer_minutes=30,
        failure_reasons=["delta_exceeded"],
    )
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    body = card["attachments"][0]["content"]["body"]
    container = next(b for b in body if b.get("type") == "Container")
    flat = str(container)
    assert "bw-prj-001.bw.PZEVENTID" in flat
    # 이메일과 동일한 메타 라인 라벨이 포함되어야 한다.
    assert "예상 배치 시각" in flat
    assert "07:00" in flat
    assert "버퍼" in flat
    assert "30분" in flat
    assert "점검 시각" in flat
    assert "점검 윈도우 기준" not in flat


def test_teams_cards_split_when_payload_exceeds_budget() -> None:
    """리포트의 OK 행이 많을 때 Teams 페이로드를 ~22KB 이하로 분할해야 한다."""
    rows = [_row("fail", failure_reasons=["x"], table_name=f"FAIL_{i:02d}") for i in range(2)]
    rows += [_row("ok", table_name=f"OK_{i:03d}") for i in range(200)]
    cards = build_teams_cards(
        trigger_kind="report", expected=NOW, actual=NOW, rows=rows
    )
    import json
    sizes = [len(json.dumps(c, ensure_ascii=False).encode("utf-8")) for c in cards]
    assert len(cards) > 1, "큰 리포트는 분할되어야 함"
    assert max(sizes) <= 25_000, f"각 청크가 25KB 이하: sizes={sizes}"
    # 후속 카드는 (i/N) 표식이 트리거 라벨에 부착되어야 한다.
    for i, c in enumerate(cards, start=1):
        body = c["attachments"][0]["content"]["body"]
        label = next(b for b in body if b.get("size") == "Small")
        assert f"({i}/{len(cards)})" in label["text"]


def test_teams_cards_returns_single_card_when_small() -> None:
    rows = [_row("fail", failure_reasons=["x"])]
    cards = build_teams_cards(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    assert len(cards) == 1


def test_teams_card_renders_ok_rows_as_full_containers_for_report() -> None:
    """리포트의 OK 행도 FAIL/INSUFFICIENT 와 동일한 풀 Container 로 렌더.

    프로젝트·데이터셋·테이블·배치 메타·이전/금일 row count + 유입 시각·증감
    Δrows·Δ% 까지 모두 노출되어야 한다.
    """
    rows = [
        _row(
            "ok",
            project="bw-prj-001",
            table_name=f"OK_{i}",
            batch_time=time(7, 0),
            buffer_minutes=30,
            yesterday_row_count=1000,
            today_row_count=1050,
            delta_percent_vs_yesterday=5.0,
            yesterday_last_modified=datetime(2026, 5, 5, 7, 4, tzinfo=KST),
            today_last_modified=datetime(2026, 5, 6, 7, 6, tzinfo=KST),
        )
        for i in range(3)
    ]
    card = build_teams_card(
        trigger_kind="report", expected=NOW, actual=NOW, rows=rows
    )
    body = card["attachments"][0]["content"]["body"]
    ok_header_idx = next(
        i
        for i, b in enumerate(body)
        if b.get("type") == "TextBlock" and b.get("text", "").startswith("OK (")
    )
    ok_containers = body[ok_header_idx + 1 :]
    assert len(ok_containers) == 3
    assert all(c["type"] == "Container" for c in ok_containers)
    # 한 컨테이너에 fqn, 배치 메타, 이전/금일 비교, 증감 라인이 모두 노출되는지.
    flat = str(ok_containers[0])
    assert "bw-prj-001.bw.OK_0" in flat
    assert "예상 배치 시각" in flat
    assert "07:00" in flat
    assert "버퍼" in flat
    assert "30분" in flat
    assert "이전 배치" in flat
    assert "금일 배치" in flat
    assert "1,000" in flat  # 이전 row count
    assert "1,050" in flat  # 금일 row count
    assert "+50" in flat  # Δrows (signed)
    assert "+5.00%" in flat  # Δ%
    assert "유입 2026-05-05 07:04:00" in flat
    assert "유입 2026-05-06 07:06:00" in flat


def test_teams_card_uses_full_width_for_teams() -> None:
    """msteams.width=Full 이 설정되어야 채팅창 폭에 맞춰 카드가 확장됨."""
    rows = [_row("fail", failure_reasons=["x"])]
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    content = card["attachments"][0]["content"]
    assert content.get("msteams", {}).get("width") == "Full"


def test_email_html_renders_failure_reasons_and_informational_notes_separately() -> None:
    """실패 사유(빨간 ⚠)와 정보성 노트(파란 ⓘ)는 별도 라벨/색상 영역으로 렌더."""
    row = _row(
        "fail",
        failure_reasons=["오늘 미적재"],
        informational_notes=["이전 배치 기록 없음 - 증감률 비교 생략"],
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "⚠ 오늘 미적재" in html
    assert "ⓘ 이전 배치 기록 없음 - 증감률 비교 생략" in html
    # 실패 사유 pill 색상(빨강 #c62828) 과 정보성 pill 색상(파랑 #075985) 이 함께 등장.
    assert "#c62828" in html
    assert "#075985" in html
    assert "실패 사유" in html
    assert "참고" in html


def test_email_html_omits_info_section_when_empty() -> None:
    row = _row("fail", failure_reasons=["x"], informational_notes=None)
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    # 참고 섹션 라벨이 없는 카드.
    assert "ⓘ" not in html


def test_teams_card_renders_informational_notes_distinctly() -> None:
    row = _row(
        "fail",
        failure_reasons=["오늘 미적재"],
        informational_notes=["이전 배치 기록 없음 - 증감률 비교 생략"],
    )
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    container = next(
        b
        for b in card["attachments"][0]["content"]["body"]
        if b.get("type") == "Container"
    )
    fail_text = next(
        item
        for item in container["items"]
        if item.get("type") == "TextBlock" and item.get("color") == "Attention"
    )
    info_text = next(
        item
        for item in container["items"]
        if item.get("type") == "TextBlock" and item.get("color") == "Accent"
    )
    assert "오늘 미적재" in fail_text["text"]
    assert "이전 배치 기록 없음" in info_text["text"]
    assert "ⓘ" in info_text["text"]
    assert "⚠" in fail_text["text"]


def test_email_html_includes_condition_query_when_set() -> None:
    """테이블에 condition_query 가 있으면 카드 본문에 함께 노출되어야 한다."""
    query = "SELECT COUNT(*) FROM `prj.bw.PZEVENTID` WHERE DT = CURRENT_DATE('Asia/Seoul')"
    row = _row(
        "fail",
        failure_reasons=["row count 0"],
        condition_query=query,
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "사용자 정의 row_count 쿼리" in html
    # autoescape 로 인코딩된 백틱/괄호도 그대로 포함되어 있어야 한다.
    assert "PZEVENTID" in html
    assert "CURRENT_DATE" in html
    assert "<pre" in html


def test_email_html_escapes_condition_query() -> None:
    """condition_query 의 위험 토큰도 jinja autoescape 로 무력화되어야 한다."""
    row = _row(
        "fail",
        failure_reasons=["x"],
        condition_query="SELECT 1 -- <script>alert(1)</script>",
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_email_html_omits_condition_query_block_when_absent() -> None:
    row = _row("fail", failure_reasons=["x"], condition_query=None)
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "사용자 정의 row_count 쿼리" not in html


def test_teams_card_includes_condition_query_when_set() -> None:
    """Teams 컨테이너에도 monospace TextBlock 으로 condition_query 가 포함되어야 한다."""
    query = "SELECT COUNT(*) FROM `prj.bw.PZEVENTID` WHERE DT = CURRENT_DATE('Asia/Seoul')"
    row = _row(
        "fail",
        failure_reasons=["row count 0"],
        condition_query=query,
    )
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    container = next(
        b for b in card["attachments"][0]["content"]["body"]
        if b.get("type") == "Container"
    )
    mono = next(
        (item for item in container["items"] if item.get("fontType") == "Monospace"),
        None,
    )
    assert mono is not None, "monospace TextBlock 으로 쿼리가 렌더되어야 한다"
    assert "PZEVENTID" in mono["text"]
    label_texts = [item.get("text", "") for item in container["items"]]
    assert any("사용자 정의 row_count 쿼리" in t for t in label_texts)


def test_teams_card_omits_condition_query_when_absent() -> None:
    row = _row("fail", failure_reasons=["x"], condition_query=None)
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    container = next(
        b for b in card["attachments"][0]["content"]["body"]
        if b.get("type") == "Container"
    )
    label_texts = [item.get("text", "") for item in container["items"]]
    assert not any("사용자 정의 row_count 쿼리" in t for t in label_texts)


def test_teams_card_includes_delta_line() -> None:
    """이메일과 동일하게 Δrows · Δ% 가 한 줄에 결합되어 노출되어야 한다."""
    row = _row(
        "fail",
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=-10.0,
        failure_reasons=["delta_exceeded"],
    )
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    body = card["attachments"][0]["content"]["body"]
    container = next(b for b in body if b.get("type") == "Container")
    flat = " ".join(item.get("text", "") for item in container["items"])
    assert "-100" in flat
    assert "-10.00%" in flat
    assert "증감" in flat
