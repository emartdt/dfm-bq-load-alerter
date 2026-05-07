import pytest
from pytest_httpx import HTTPXMock

from dfm_bq_load_alerter.notifier.teams import TeamsPostError, post_teams_card


@pytest.mark.asyncio
async def test_post_teams_card_rejects_empty_url() -> None:
    with pytest.raises(ValueError):
        await post_teams_card(webhook_url="", payload={"x": 1})


@pytest.mark.asyncio
async def test_post_teams_card_succeeds_on_2xx(httpx_mock: HTTPXMock) -> None:
    url = "https://outlook.office.com/webhook/abc"
    httpx_mock.add_response(method="POST", url=url, status_code=200, text="OK")
    await post_teams_card(webhook_url=url, payload={"type": "message"})


@pytest.mark.asyncio
async def test_post_teams_card_raises_on_4xx(httpx_mock: HTTPXMock) -> None:
    url = "https://outlook.office.com/webhook/abc"
    httpx_mock.add_response(method="POST", url=url, status_code=400, text="bad")
    with pytest.raises(TeamsPostError):
        await post_teams_card(webhook_url=url, payload={"type": "message"})


@pytest.mark.asyncio
async def test_post_teams_card_raises_on_5xx(httpx_mock: HTTPXMock) -> None:
    url = "https://outlook.office.com/webhook/abc"
    httpx_mock.add_response(method="POST", url=url, status_code=500, text="server error")
    with pytest.raises(TeamsPostError):
        await post_teams_card(webhook_url=url, payload={"type": "message"})


@pytest.mark.asyncio
async def test_post_teams_card_wraps_connect_timeout(httpx_mock: HTTPXMock) -> None:
    """Transport-level failures (DNS, connect/read timeout) must be wrapped
    in TeamsPostError so the dispatcher's `except TeamsPostError` catches them
    and records a failed AlertEvent instead of bubbling up to a 500."""
    import httpx as httpx_module

    url = "https://outlook.office.com/webhook/abc"
    httpx_mock.add_exception(httpx_module.ConnectTimeout("connect timeout"))
    with pytest.raises(TeamsPostError) as excinfo:
        await post_teams_card(webhook_url=url, payload={"type": "message"})
    assert "ConnectTimeout" in str(excinfo.value) or "connect timeout" in str(excinfo.value)
