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
