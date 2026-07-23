import httpx
import pytest

from app.trello_client import TrelloClient, TrelloError


def client_with(handler):
    client = TrelloClient("api-key", "secret-token", "list")
    old = client._client
    client._client = httpx.AsyncClient(base_url=client.BASE_URL, transport=httpx.MockTransport(handler))
    return client, old


@pytest.mark.asyncio
async def test_authorization_list_members_and_card():
    async def handler(request):
        payloads = {
            "/1/members/me": {"id": "me", "username": "user"},
            "/1/lists/list": {"id": "list", "name": "Tasks", "idBoard": "board", "closed": False},
            "/1/boards/board/members": [{"id": "member", "fullName": "Name"}],
            "/1/cards/card": {"id": "card", "name": "Task", "url": "https://trello.com/c/card"},
        }
        assert request.url.params["key"] == "api-key"
        assert request.url.params["token"] == "secret-token"
        return httpx.Response(200, json=payloads[request.url.path])

    client, old = client_with(handler)
    await old.aclose()
    assert (await client.check_authorization())["id"] == "me"
    assert (await client.check_ready())["name"] == "Tasks"
    assert (await client.get_members())[0]["id"] == "member"
    assert (await client.get_card("card"))["id"] == "card"
    await client.close()


@pytest.mark.asyncio
async def test_create_card_payload_and_iso_due():
    async def handler(request):
        assert request.url.path == "/1/cards"
        assert "secret-token" not in request.content.decode()
        body = request.content.decode()
        assert "2026-12-31T18%3A00%3A00%2B03%3A00" in body
        assert "idMembers=member" in body
        return httpx.Response(200, json={"id": "card-id", "url": "https://trello.com/c/safe"})

    client, old = client_with(handler)
    await old.aclose()
    assert (await client.create_card("Name", "Desc", "2026-12-31T18:00:00+03:00", "member"))["id"] == "card-id"
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500])
async def test_http_errors_are_safe(status):
    client, old = client_with(lambda request: httpx.Response(status, json={"token": "secret-token"}))
    await old.aclose()
    with pytest.raises(TrelloError) as caught:
        await client.check_authorization()
    assert "secret-token" not in str(caught.value)
    assert "api-key" not in str(caught.value)
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [httpx.Response(200, text="not-json"), httpx.Response(200, json="wrong")])
async def test_invalid_json(response):
    client, old = client_with(lambda request: response)
    await old.aclose()
    with pytest.raises(TrelloError, match="(некорректный|формат)"):
        await client.check_authorization()
    await client.close()


@pytest.mark.asyncio
async def test_create_response_requires_id():
    client, old = client_with(lambda request: httpx.Response(200, json={"url": "safe"}))
    await old.aclose()
    with pytest.raises(TrelloError, match="ID"):
        await client.create_card("Name", "Desc", None, None)
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("exception, message", [(httpx.ReadTimeout("timeout"), "время"), (httpx.ConnectError("network"), "сетевая")])
async def test_transport_errors(exception, message):
    def handler(request):
        raise exception
    client, old = client_with(handler)
    await old.aclose()
    with pytest.raises(TrelloError, match=message):
        await client.check_authorization()
    await client.close()
