from __future__ import annotations

from typing import Any

import httpx


class TrelloError(RuntimeError):
    """Safe Trello error suitable for displaying to a user."""


class TrelloClient:
    BASE_URL = "https://api.trello.com/1"

    def __init__(self, key: str, token: str, list_id: str, timeout: float = 15.0):
        self.list_id = list_id
        self._auth = {"key": key, "token": token}
        self._client = httpx.AsyncClient(base_url=self.BASE_URL, timeout=httpx.Timeout(timeout))

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        params = {**self._auth, **kwargs.pop("params", {})}
        try:
            response = await self._client.request(method, path, params=params, **kwargs)
        except httpx.TimeoutException as exc:
            raise TrelloError("истекло время ожидания ответа Trello") from exc
        except httpx.RequestError as exc:
            raise TrelloError("сетевая ошибка при обращении к Trello") from exc
        messages = {400: "Trello отклонил данные карточки", 401: "неверные учётные данные Trello", 403: "недостаточно прав в Trello", 404: "объект Trello не найден", 429: "превышен лимит запросов Trello"}
        if response.status_code in messages:
            raise TrelloError(messages[response.status_code])
        if response.status_code >= 500:
            raise TrelloError("Trello временно недоступен")
        if response.is_error:
            raise TrelloError(f"неожиданный ответ Trello (HTTP {response.status_code})")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TrelloError("Trello вернул некорректный ответ") from exc
        if not isinstance(payload, (dict, list)):
            raise TrelloError("Trello вернул неожиданный формат данных")
        return payload

    async def check_authorization(self) -> dict[str, Any]:
        return await self._request("GET", "/members/me", params={"fields": "id,username"})

    async def check_list(self) -> dict[str, Any]:
        return await self._request("GET", f"/lists/{self.list_id}", params={"fields": "id,name,closed,idBoard"})

    async def check_ready(self) -> dict[str, Any]:
        await self.check_authorization()
        result = await self.check_list()
        if result.get("closed"):
            raise TrelloError("настроенный список Trello закрыт")
        return result

    async def create_card(self, name: str, description: str, due: str | None, member_id: str | None) -> dict[str, Any]:
        data: dict[str, Any] = {"idList": self.list_id, "name": name, "desc": description}
        if due:
            data["due"] = due
        if member_id:
            data["idMembers"] = member_id
        result = await self._request("POST", "/cards", data=data)
        if not isinstance(result.get("id"), str):
            raise TrelloError("Trello не вернул ID созданной карточки")
        return result

    async def get_members(self) -> list[dict[str, Any]]:
        board_id = (await self.check_list()).get("idBoard")
        if not board_id:
            raise TrelloError("не удалось определить доску Trello")
        return await self._request("GET", f"/boards/{board_id}/members", params={"fields": "id,fullName,username"})

    async def get_card(self, card_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/cards/{card_id}", params={"fields": "id,name,url,due"})
