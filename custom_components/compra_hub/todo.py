"""Listas de la compra y tareas del hub como listas de tareas de HA."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PERSONAL
from .coordinator import CompraHubConfigEntry, CompraHubCoordinator
from .entity import CompraHubEntity

PARALLEL_UPDATES = 0


def _upsert(rows: list[dict[str, Any]], row: dict[str, Any]) -> list[dict[str, Any]]:
    """Sustituye la fila con el mismo id o la añade al final."""
    if any(r["id"] == row["id"] for r in rows):
        return [row if r["id"] == row["id"] else r for r in rows]
    return [*rows, row]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CompraHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[TodoListEntity] = [
        ShoppingListEntity(coordinator, key) for key in coordinator.data.lists
    ]
    entities += [TasksEntity(coordinator, scope) for scope in coordinator.data.tasks]
    async_add_entities(entities)


class ShoppingListEntity(CompraHubEntity, TodoListEntity):
    """Una lista de la compra (personal o de grupo). La cantidad va en la descripción."""

    _attr_icon = "mdi:cart-outline"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator: CompraHubCoordinator, list_key: str) -> None:
        super().__init__(coordinator, "compra", f"lista:{list_key}")
        self._list_key = list_key
        lst = coordinator.data.lists[list_key]
        personal = [k for k in coordinator.data.lists if k.startswith("p:")]
        # Con una sola lista personal, sin nombre: la entidad es «Compra».
        self._attr_name = None if not lst["group"] and len(personal) == 1 else lst["name"]

    @property
    def available(self) -> bool:
        return super().available and self._list_key in self.coordinator.data.lists

    @property
    def todo_items(self) -> list[TodoItem] | None:
        lst = self.coordinator.data.lists.get(self._list_key)
        if lst is None:
            return None
        return [
            TodoItem(
                uid=item["id"],
                summary=item["name"],
                description=item.get("qty") or None,
                status=TodoItemStatus.COMPLETED if item["done"] else TodoItemStatus.NEEDS_ACTION,
            )
            for item in lst["items"]
        ]

    def _apply(self, rows: list[dict[str, Any]]) -> None:
        # Cambio local inmediato (la API devuelve el producto ya guardado) y
        # refresco completo después, que llega con unos segundos de retraso.
        self.coordinator.data.lists[self._list_key]["items"] = rows
        self.coordinator.async_update_listeners()

    def _rows(self) -> list[dict[str, Any]]:
        return self.coordinator.data.lists[self._list_key]["items"]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        saved = await self.coordinator.api.add_item(self._list_key, item.summary or "", item.description)
        self._apply(_upsert(self._rows(), saved))
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        changes: dict[str, Any] = {"done": item.status == TodoItemStatus.COMPLETED}
        if item.summary:
            changes["name"] = item.summary
        # El hub no borra la cantidad con null (COALESCE): "" la deja vacía.
        changes["qty"] = item.description or ""
        saved = await self.coordinator.api.update_item(self._list_key, item.uid or "", changes)
        self._apply(_upsert(self._rows(), saved))
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        # Igual que «Vaciar comprados» en la app: un producto fijo (📌, p. ej.
        # la leche) que ya está comprado no se borra, se desmarca y se queda
        # para la próxima compra. Para quitarlo del todo, se desfija en la app.
        rows = {r["id"]: r for r in self._rows()}
        for uid in uids:
            row = rows.get(uid)
            if row and row.get("recurring") and row.get("done"):
                rows[uid] = await self.coordinator.api.update_item(self._list_key, uid, {"done": False})
            else:
                await self.coordinator.api.delete_item(self._list_key, uid)
                rows.pop(uid, None)
        self._apply(list(rows.values()))
        await self.coordinator.async_request_refresh()


class TasksEntity(CompraHubEntity, TodoListEntity):
    """Tareas personales o de un grupo. «Haciendo» cuenta como pendiente."""

    _attr_icon = "mdi:checkbox-marked-circle-outline"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
    )

    def __init__(self, coordinator: CompraHubCoordinator, scope: str) -> None:
        super().__init__(coordinator, "tareas", f"tareas:{scope}")
        self._scope = scope
        self._group_id = None if scope == PERSONAL else scope
        self._attr_name = self.group_name(self._group_id)  # None -> «Tareas»

    @property
    def available(self) -> bool:
        return super().available and self._scope in self.coordinator.data.tasks

    def _tasks(self) -> dict[str, dict[str, Any]]:
        return {t["id"]: t for t in self.coordinator.data.tasks.get(self._scope, [])}

    def _apply(self, rows: list[dict[str, Any]]) -> None:
        self.coordinator.data.tasks[self._scope] = rows
        self.coordinator.async_update_listeners()

    @property
    def todo_items(self) -> list[TodoItem] | None:
        if self._scope not in self.coordinator.data.tasks:
            return None
        return [
            TodoItem(
                uid=t["id"],
                summary=t["title"],
                status=TodoItemStatus.COMPLETED if t["status"] == "done" else TodoItemStatus.NEEDS_ACTION,
                due=date.fromisoformat(t["dueDate"]) if t.get("dueDate") else None,
            )
            for t in self.coordinator.data.tasks[self._scope]
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        due = item.due.isoformat() if isinstance(item.due, date) else None
        saved = await self.coordinator.api.add_task(self._group_id, item.summary or "", due)
        self._apply(_upsert(self.coordinator.data.tasks[self._scope], saved))
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        current = self._tasks().get(item.uid or "", {})
        changes: dict[str, Any] = {}
        if item.summary and item.summary != current.get("title"):
            changes["title"] = item.summary
        if item.status == TodoItemStatus.COMPLETED and current.get("status") != "done":
            changes["status"] = "done"
        elif item.status == TodoItemStatus.NEEDS_ACTION and current.get("status") == "done":
            changes["status"] = "todo"
        due = item.due.isoformat() if isinstance(item.due, date) else None
        if due != current.get("dueDate"):
            changes["dueDate"] = due
        if changes:
            saved = await self.coordinator.api.update_task(self._group_id, item.uid or "", changes)
            self._apply(_upsert(self.coordinator.data.tasks[self._scope], saved))
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self.coordinator.api.delete_task(self._group_id, uid)
        self._apply([t for t in self.coordinator.data.tasks[self._scope] if t["id"] not in uids])
        await self.coordinator.async_request_refresh()
