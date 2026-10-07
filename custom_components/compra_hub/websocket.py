"""Comando WebSocket para la tarjeta: qué entidades son de qué cuenta."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import actions
from .const import CONF_HUB, PERSONAL


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_info)


@websocket_api.websocket_command(
    {vol.Required("type"): "compra_hub/info", vol.Optional("entry_id"): str}
)
@callback
def ws_info(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    try:
        coordinator = actions.resolve_coordinator(hass, msg.get("entry_id"), connection.user.id)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    entry = coordinator.config_entry
    data = coordinator.data
    prefix = f"{entry.unique_id}:"
    by_key = {
        e.unique_id[len(prefix):]: e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.unique_id.startswith(prefix)
    }

    def scope_name(scope: str) -> str | None:
        return None if scope == PERSONAL else data.groups.get(scope)

    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "hub": entry.data[CONF_HUB],
            "username": data.profile.get("username"),
            "user_id": data.profile.get("id"),
            "groups": [
                {"id": gid, "name": name, "members": [m["username"] for m in data.members.get(gid, [])]}
                for gid, name in data.groups.items()
            ],
            "lists": [
                {"entity_id": by_key.get(f"lista:{key}"), "name": lst["name"], "group": data.groups.get(lst["group"])}
                for key, lst in data.lists.items()
                if by_key.get(f"lista:{key}")
            ],
            "tasks": [
                {"entity_id": by_key.get(f"tareas:{scope}"), "group": scope_name(scope)}
                for scope in data.tasks
                if by_key.get(f"tareas:{scope}")
            ],
            "calendars": [
                {"entity_id": by_key.get(f"calendario:{scope}"), "group": scope_name(scope)}
                for scope in data.notes
                if by_key.get(f"calendario:{scope}")
            ],
            "meals": [
                {
                    "group": scope_name(scope),
                    "comida": by_key.get(f"menu:{scope}:comida"),
                    "cena": by_key.get(f"menu:{scope}:cena"),
                }
                for scope in data.meals
            ],
            "month_spent": by_key.get("gastado_mes"),
            "tasks_today": by_key.get("para_hoy"),
            "balances": [
                {"group": name, "group_id": gid, "balance": by_key.get(f"saldo:{gid}"), "debts": by_key.get(f"deudas:{gid}")}
                for gid, name in data.groups.items()
            ],
        },
    )
