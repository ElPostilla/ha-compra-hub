"""Sondeo periódico de todo lo que muestra la integración."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HubApi, HubAuthError, HubError
from .const import DOMAIN, LOGGER, MEAL_SLOTS, PERSONAL, UPDATE_INTERVAL


@dataclass
class HubData:
    """Foto del hub para una cuenta.

    Las claves de "scope" son PERSONAL o el id de un grupo. Las listas de la
    compra van por clave propia: "p:<id de lista>" (personales, puede haber
    varias) o "g:<id de grupo>" (una por grupo).
    """

    profile: dict[str, Any]
    groups: dict[str, str] = field(default_factory=dict)  # id -> nombre
    lists: dict[str, dict[str, Any]] = field(default_factory=dict)
    tasks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    notes: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    meals: dict[str, dict[str, str | None]] = field(default_factory=dict)
    balances: dict[str, int] = field(default_factory=dict)  # grupo -> céntimos
    month_spent_cents: int = 0


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

        for lst in personal_lists:
            data.lists[f"p:{lst['id']}"] = {"name": lst["name"], "items": lst["items"], "group": None}

        scopes: list[str | None] = [None, *data.groups]
        results = await asyncio.gather(
            *(api.group_list(gid) for gid in data.groups),
            *(api.tasks(s) for s in scopes),
            *(api.notes(s) for s in scopes),
            *(api.meals(s, today, today) for s in scopes),
        )
        n_groups, n_scopes = len(data.groups), len(scopes)
        group_lists = results[:n_groups]
        tasks = results[n_groups : n_groups + n_scopes]
        notes = results[n_groups + n_scopes : n_groups + 2 * n_scopes]
        meals = results[n_groups + 2 * n_scopes :]

        for gid, glist in zip(data.groups, group_lists, strict=True):
            data.lists[f"g:{gid}"] = {"name": data.groups[gid], "items": glist["items"], "group": gid}
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

        # Si cambian los grupos (te unes a uno nuevo, sales de otro), las
        # entidades se crean al cargar: se recarga la entrada para que
        # aparezcan o desaparezcan.
        if self.data is not None and set(self.data.groups) != set(data.groups):
            LOGGER.info("Han cambiado los grupos del hub; recargando la integración")
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return data
