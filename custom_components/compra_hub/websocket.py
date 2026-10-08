"""Comandos WebSocket para la tarjeta: qué entidades son de qué cuenta y el
detalle de una lista de la compra (pasillo y fijados, que la entidad todo no da)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from . import actions
from .const import CONF_HUB, DOMAIN, PERSONAL


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_list)


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


@websocket_api.websocket_command({vol.Required("type"): "compra_hub/list", vol.Required("entity_id"): str})
@callback
def ws_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Productos de una lista con su pasillo (category) y si están fijados (recurring)."""
    reg_entry = er.async_get(hass).async_get(msg["entity_id"])
    entry = hass.config_entries.async_get_entry(reg_entry.config_entry_id) if reg_entry else None
    prefix = f"{entry.unique_id}:lista:" if entry and entry.domain == DOMAIN else None
    if not prefix or not reg_entry.unique_id.startswith(prefix) or not hasattr(entry, "runtime_data"):
        connection.send_error(msg["id"], "not_found", "Esa entidad no es una lista de la compra del hub.")
        return
    lst = entry.runtime_data.data.lists.get(reg_entry.unique_id[len(prefix):])
    if lst is None:
        connection.send_error(msg["id"], "not_found", "Esa lista ya no existe en el hub.")
        return
    connection.send_result(
        msg["id"],
        {
            "name": lst["name"],
            "items": [
                {
                    "id": i["id"],
                    "name": i["name"],
                    "qty": i.get("qty") or "",
                    "category": i.get("category") or "otros",
                    "done": bool(i.get("done")),
                    "recurring": bool(i.get("recurring")),
                }
                for i in lst["items"]
            ],
        },
    )
