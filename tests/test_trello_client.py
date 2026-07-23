import httpx
import pytest

from app.trello_client import TrelloClient, TrelloError


@pytest.mark.asyncio
async def test_create_card_is_mocked():
    client = TrelloClient("key", "token", "list")
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/1/cards"
        return httpx.Response(200, json={"id": "card-id", "url": "https://trello.com/c/safe"})
    await client._client.aclose()
    client._client = httpx.AsyncClient(base_url=client.BASE_URL, transport=httpx.MockTransport(handler))
    assert (await client.create_card("Name", "Desc", None, None))["id"] == "card-id"
    await client.close()


@pytest.mark.asyncio
async def test_http_error_is_safe():
    client = TrelloClient("key", "secret-token", "list")
    await client._client.aclose()
    client._client = httpx.AsyncClient(base_url=client.BASE_URL, transport=httpx.MockTransport(lambda request: httpx.Response(401, json={})))
    with pytest.raises(TrelloError, match="учётные данные"):
        await client.check_authorization()
    await client.close()
