"""Cliente HTTP de las APIs del hub.

Cada petición lleva el access token de Keycloak como "Authorization:
Bearer". oauth2-proxy (delante del hub) lo valida y se lo pasa a cada API
igual que el de una sesión del navegador. Sin token válido responde con una
redirección al login, que aquí se trata como error de autenticación.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


class HubError(Exception):
    """Error al hablar con el hub."""


class HubAuthError(HubError):
    """El hub no acepta el token (sesión caducada o revocada)."""


class HubApi:
    """Acceso a lista-compra-api, todo-api, calendario-api, gastos-api y menu-api."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        hub: str,
        oauth: OAuth2Session | None = None,
        token: str | None = None,
    ) -> None:
        self._session = session
        self._base = f"https://{hub}"
        self._oauth = oauth
        self._token = token

    async def _access_token(self) -> str:
        if self._oauth is None:
            assert self._token is not None
            return self._token
        await self._oauth.async_ensure_token_valid()
        return self._oauth.token["access_token"]

    async def request(self, method: str, path: str, json: Any = None) -> Any:
        token = await self._access_token()
        try:
            async with self._session.request(
                method,
                self._base + path,
                json=json,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status in (301, 302, 303, 307, 401, 403):
                    raise HubAuthError(f"{method} {path}: HTTP {resp.status}")
                if resp.status >= 400:
                    text = await resp.text()
                    raise HubError(f"{method} {path}: HTTP {resp.status} {text[:200]}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HubError(f"{method} {path}: {err}") from err

    # ---------------------------------------------------------- lectura

    async def profile(self) -> dict[str, Any]:
        return await self.request("GET", "/api/profile")

    async def groups(self) -> list[dict[str, Any]]:
        return (await self.request("GET", "/api/groups"))["groups"]

    async def personal_lists(self) -> list[dict[str, Any]]:
        return (await self.request("GET", "/api/personal/lists"))["lists"]

    async def group_list(self, group_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/api/groups/{group_id}/list")

    async def tasks(self, group_id: str | None) -> list[dict[str, Any]]:
        path = f"/api-todo/groups/{group_id}/tasks" if group_id else "/api-todo/tasks"
        return (await self.request("GET", path))["tasks"]

    async def notes(self, group_id: str | None) -> dict[str, list[dict[str, Any]]]:
        path = f"/api-calendario/groups/{group_id}/notes" if group_id else "/api-calendario/notes"
        return (await self.request("GET", path))["notes"]

    async def meals(self, group_id: str | None, start: str, end: str) -> list[dict[str, Any]]:
        base = f"/api-menu/groups/{group_id}/meals" if group_id else "/api-menu/meals"
        return (await self.request("GET", f"{base}?start={start}&end={end}"))["meals"]

    async def balances(self) -> list[dict[str, Any]]:
        return (await self.request("GET", "/api-gastos/groups/balances"))["balances"]

    async def expenses(self) -> list[dict[str, Any]]:
        return (await self.request("GET", "/api-gastos/expenses"))["expenses"]

    # ------------------------------------------------- lista de la compra

    def _items_path(self, list_key: str) -> str:
        scope, ident = list_key.split(":", 1)
        if scope == "g":
            return f"/api/groups/{ident}/list/items"
        return f"/api/personal/lists/{ident}/items"

    async def add_item(self, list_key: str, name: str, qty: str | None) -> dict[str, Any]:
        return await self.request("POST", self._items_path(list_key), {"name": name, "qty": qty})

    async def update_item(self, list_key: str, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", f"{self._items_path(list_key)}/{item_id}", changes)

    async def delete_item(self, list_key: str, item_id: str) -> None:
        await self.request("DELETE", f"{self._items_path(list_key)}/{item_id}")

    # ----------------------------------------------------------- tareas

    def _tasks_path(self, group_id: str | None) -> str:
        return f"/api-todo/groups/{group_id}/tasks" if group_id else "/api-todo/tasks"

    async def add_task(self, group_id: str | None, title: str, due: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title}
        if due:
            body["dueDate"] = due
        return await self.request("POST", self._tasks_path(group_id), body)

    async def update_task(self, group_id: str | None, task_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", f"{self._tasks_path(group_id)}/{task_id}", changes)

    async def delete_task(self, group_id: str | None, task_id: str) -> None:
        await self.request("DELETE", f"{self._tasks_path(group_id)}/{task_id}")
