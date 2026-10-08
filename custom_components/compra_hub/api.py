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

from .categories import detect_category

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

    # "lst" es la entrada de HubData.lists: {"group": id de grupo o None,
    # "list_id": id de la lista personal}.
    def _items_path(self, lst: dict[str, Any]) -> str:
        if lst["group"]:
            return f"/api/groups/{lst['group']}/list/items"
        return f"/api/personal/lists/{lst['list_id']}/items"

    async def create_personal_list(self, name: str) -> dict[str, Any]:
        return await self.request("POST", "/api/personal/lists", {"name": name})

    async def add_item(self, lst: dict[str, Any], name: str, qty: str | None) -> dict[str, Any]:
        # Como la app: el pasillo se deduce del nombre al añadirlo.
        body = {"name": name, "qty": qty, "category": detect_category(name)}
        return await self.request("POST", self._items_path(lst), body)

    async def update_item(self, lst: dict[str, Any], item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", f"{self._items_path(lst)}/{item_id}", changes)

    async def delete_item(self, lst: dict[str, Any], item_id: str) -> None:
        await self.request("DELETE", f"{self._items_path(lst)}/{item_id}")

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

    # ----------------------------------------------------- recordatorios

    def _notes_path(self, group_id: str | None) -> str:
        return f"/api-calendario/groups/{group_id}/notes" if group_id else "/api-calendario/notes"

    async def add_note(self, group_id: str | None, body: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", self._notes_path(group_id), body)

    async def update_note(self, group_id: str | None, note_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PUT", f"{self._notes_path(group_id)}/{note_id}", body)

    async def delete_note(self, group_id: str | None, note_id: str) -> None:
        await self.request("DELETE", f"{self._notes_path(group_id)}/{note_id}")

    # ------------------------------------------------------------ gastos

    async def group_balance(self, group_id: str) -> dict[str, Any]:
        """{"balances": [{userId, username, balanceCents}], "debts": [...]}"""
        return await self.request("GET", f"/api-gastos/groups/{group_id}/balance")

    async def group_expenses(self, group_id: str) -> list[dict[str, Any]]:
        return (await self.request("GET", f"/api-gastos/groups/{group_id}/expenses"))["expenses"]

    async def add_expense(self, group_id: str | None, body: dict[str, Any]) -> dict[str, Any]:
        path = f"/api-gastos/groups/{group_id}/expenses" if group_id else "/api-gastos/expenses"
        return await self.request("POST", path, body)

    async def set_share_settled(self, group_id: str, expense_id: str, user_id: str, settled: bool) -> dict[str, Any]:
        return await self.request(
            "PATCH",
            f"/api-gastos/groups/{group_id}/expenses/{expense_id}/shares/{user_id}",
            {"settled": settled},
        )

    # -------------------------------------------------------------- menú

    async def set_meal(self, group_id: str | None, date: str, slot: str, title: str) -> dict[str, Any]:
        base = f"/api-menu/groups/{group_id}/meals" if group_id else "/api-menu/meals"
        return await self.request("PUT", f"{base}/{date}/{slot}", {"title": title})

