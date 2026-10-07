"""Sondeo periódico de todo lo que muestra la integración."""

from __future__ import annotations

import asyncio
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HubApi, HubAuthError, HubError
from .const import (
    DEFAULT_PERSONAL_LIST,
    DOMAIN,
    LOGGER,
    MEAL_SLOTS,
    PERSONAL,
    SINGLE_PERSONAL_KEY,
    UPDATE_INTERVAL,
)


@dataclass
class HubData:
    """Foto del hub para una cuenta.

    Las claves de "scope" son PERSONAL o el id de un grupo. Las listas de la
    compra van por clave propia: "g:<id de grupo>" (una por grupo) y, las
    personales, "p:" si hay una sola o ninguna todavía (list_id None: se
    crea al añadir el primer producto, como hace la app al abrirla) o
    "p:<id de lista>" si hay varias.
    """

    profile: dict[str, Any]
    groups: dict[str, str] = field(default_factory=dict)  # id -> nombre
    lists: dict[str, dict[str, Any]] = field(default_factory=dict)
    tasks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    notes: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    meals: dict[str, dict[str, str | None]] = field(default_factory=dict)
    balances: dict[str, int] = field(default_factory=dict)  # grupo -> céntimos
    month_spent_cents: int = 0
    # Por grupo: miembros [{userId, username}] y deudas pendientes persona a
    # persona [{fromUserId, fromUsername, toUserId, toUsername, amountCents}].
    members: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    debts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def tasks_due(self, today: str) -> list[dict[str, Any]]:
        """Tareas sin terminar que vencen hoy o están atrasadas, de todos los ámbitos."""
        due = []
        for scope, tasks in self.tasks.items():
            for t in tasks:
                if t["status"] != "done" and t.get("dueDate") and t["dueDate"] <= today:
                    due.append({**t, "scope": scope, "group": self.groups.get(scope)})
        return sorted(due, key=lambda t: t["dueDate"])

    def find_group(self, name: str) -> str | None:
        """Id del grupo por nombre, sin distinguir mayúsculas ni tildes."""
        wanted = _fold(name)
        exact = [gid for gid, n in self.groups.items() if _fold(n) == wanted]
        if exact:
            return exact[0]
        partial = [gid for gid, n in self.groups.items() if wanted and wanted in _fold(n)]
        return partial[0] if len(partial) == 1 else None

    def find_member(self, group_id: str, name: str) -> dict[str, Any] | None:
        wanted = _fold(name).lstrip("@")
        for m in self.members.get(group_id, []):
            if _fold(m["username"]) == wanted:
                return m
        return None


def _fold(text: str) -> str:
    """Minúsculas y sin tildes, para comparar nombres dichos en voz alta."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(text).strip().lower()) if unicodedata.category(c) != "Mn"
    )


type CompraHubConfigEntry = ConfigEntry[CompraHubCoordinator]


class CompraHubCoordinator(DataUpdateCoordinator[HubData]):
    """Pide todo cada minuto (unas pocas peticiones por grupo)."""

    config_entry: CompraHubConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CompraHubConfigEntry, api: HubApi) -> None:
        super().__init__(
            hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL
        )
        self.api = api

    async def _async_update_data(self) -> HubData:
        try:
            return await self._fetch()
        except HubAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HubError as err:
            raise UpdateFailed(str(err)) from err

    async def _fetch(self) -> HubData:
        api = self.api
        today = dt_util.now().date().isoformat()
        month = today[:7]

        profile, groups, personal_lists, balances, expenses = await asyncio.gather(
            api.profile(), api.groups(), api.personal_lists(), api.balances(), api.expenses()
        )
        data = HubData(profile=profile, groups={g["id"]: g["name"] for g in groups})

        if len(personal_lists) <= 1:
            lst = personal_lists[0] if personal_lists else None
            data.lists[SINGLE_PERSONAL_KEY] = {
                "name": lst["name"] if lst else DEFAULT_PERSONAL_LIST,
                "items": lst["items"] if lst else [],
                "group": None,
                "list_id": lst["id"] if lst else None,
            }
        else:
            for lst in personal_lists:
                data.lists[f"p:{lst['id']}"] = {
                    "name": lst["name"], "items": lst["items"], "group": None, "list_id": lst["id"]
                }

        scopes: list[str | None] = [None, *data.groups]
        results = await asyncio.gather(
            *(api.group_list(gid) for gid in data.groups),
            *(api.tasks(s) for s in scopes),
            *(api.notes(s) for s in scopes),
            *(api.meals(s, today, today) for s in scopes),
            *(api.group_balance(gid) for gid in data.groups),
        )
        n_groups, n_scopes = len(data.groups), len(scopes)
        group_lists = results[:n_groups]
        tasks = results[n_groups : n_groups + n_scopes]
        notes = results[n_groups + n_scopes : n_groups + 2 * n_scopes]
        meals = results[n_groups + 2 * n_scopes : n_groups + 3 * n_scopes]
        group_balances = results[n_groups + 3 * n_scopes :]
        for gid, gb in zip(data.groups, group_balances, strict=True):
            data.members[gid] = [{"userId": b["userId"], "username": b["username"]} for b in gb["balances"]]
            data.debts[gid] = gb.get("debts", [])

        for gid, glist in zip(data.groups, group_lists, strict=True):
            data.lists[f"g:{gid}"] = {
                "name": data.groups[gid], "items": glist["items"], "group": gid, "list_id": glist["listId"]
            }
        for scope, s_tasks, s_notes, s_meals in zip(scopes, tasks, notes, meals, strict=True):
            key = scope or PERSONAL
            data.tasks[key] = s_tasks
            data.notes[key] = s_notes
            data.meals[key] = {
                slot: next((m["title"] for m in s_meals if m["slot"] == slot and m["date"] == today), None)
                for slot in MEAL_SLOTS
            }

        data.balances = {b["groupId"]: b["balanceCents"] for b in balances}
        data.month_spent_cents = sum(
            e["amountCents"] for e in expenses if str(e.get("date", "")).startswith(month)
        )

        # Si cambian los grupos (te unes a uno nuevo, sales de otro) o el
        # número de listas personales, las entidades se crean al cargar: se
        # recarga la entrada para que aparezcan o desaparezcan.
        if self.data is not None and (
            set(self.data.groups) != set(data.groups) or set(self.data.lists) != set(data.lists)
        ):
            LOGGER.info("Han cambiado los grupos o las listas del hub; recargando la integración")
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return data
