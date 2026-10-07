"""Lógica común de las acciones (servicios) y de la voz.

Elegir la cuenta: la indicada explícitamente; si no, la vinculada al
usuario de Home Assistant que hace la petición (opción «Usuario de Home
Assistant» de la integración); si no, la única cargada. Con varias y sin
vincular, se pide elegir: tocar la cuenta equivocada sería peor que fallar.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import CATEGORIES, CONF_DEV_HUBS, CONF_HA_USER, CONF_HUB, DOMAIN, MEAL_SLOTS
from .coordinator import CompraHubCoordinator


def resolve_coordinator(
    hass: HomeAssistant, entry_id: str | None = None, user_id: str | None = None
) -> CompraHubCoordinator:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    if entry_id:
        for e in entries:
            if e.entry_id == entry_id:
                return e.runtime_data
        raise ServiceValidationError("Esa cuenta del hub no está conectada o no ha cargado.")
    if not entries:
        raise ServiceValidationError("No hay ninguna cuenta del hub conectada.")
    if user_id:
        mine = [e for e in entries if e.options.get(CONF_HA_USER) == user_id]
        # Si la misma persona tiene producción y dev, gana producción.
        mine.sort(key=lambda e: e.data[CONF_HUB] in CONF_DEV_HUBS)
        if mine:
            return mine[0].runtime_data
    if len(entries) == 1:
        return entries[0].runtime_data
    raise ServiceValidationError(
        "Hay varias cuentas del hub conectadas. Indica cuál (config_entry_id) o vincula tu "
        "usuario de Home Assistant en las opciones de la integración."
    )


def _group(coordinator: CompraHubCoordinator, name: str | None) -> str | None:
    if not name:
        return None
    if name in coordinator.data.groups:
        return name
    gid = coordinator.data.find_group(name)
    if gid is None:
        groups = ", ".join(coordinator.data.groups.values()) or "ninguno"
        raise ServiceValidationError(f"No encuentro el grupo «{name}». Tus grupos: {groups}.")
    return gid


def _member(coordinator: CompraHubCoordinator, group_id: str, name: str) -> dict[str, Any]:
    m = coordinator.data.find_member(group_id, name)
    if m is None:
        names = ", ".join(f"@{x['username']}" for x in coordinator.data.members.get(group_id, []))
        raise ServiceValidationError(f"«{name}» no es miembro de ese grupo. Miembros: {names}.")
    return m


async def add_expense(
    coordinator: CompraHubCoordinator,
    *,
    description: str,
    amount: float,
    category: str | None = None,
    date: str | None = None,
    group: str | None = None,
    paid_by: str | None = None,
    participants: list[str] | None = None,
) -> dict[str, Any]:
    cents = round(float(amount) * 100)
    if cents <= 0:
        raise ServiceValidationError("El importe tiene que ser mayor que cero.")
    category = category if category in CATEGORIES else "otros"
    body: dict[str, Any] = {
        "description": description.strip(),
        "amountCents": cents,
        "category": category,
        "date": date or dt_util.now().date().isoformat(),
        "recurrence": "none",
    }
    gid = _group(coordinator, group)
    if gid:
        if paid_by:
            body["paidBy"] = _member(coordinator, gid, paid_by)["userId"]
        if participants:
            body["participants"] = [_member(coordinator, gid, p)["userId"] for p in participants]
    elif paid_by or participants:
        raise ServiceValidationError("Quién pagó y entre quién se reparte solo tienen sentido en un grupo.")
    saved = await coordinator.api.add_expense(gid, body)
    await coordinator.async_request_refresh()
    return {**saved, "group": coordinator.data.groups.get(gid) if gid else None}


async def plan_meal(
    coordinator: CompraHubCoordinator,
    *,
    title: str,
    slot: str,
    date: str | None = None,
    group: str | None = None,
) -> dict[str, Any]:
    if slot not in MEAL_SLOTS:
        raise ServiceValidationError("La franja tiene que ser «comida» o «cena».")
    gid = _group(coordinator, group)
    saved = await coordinator.api.set_meal(gid, date or dt_util.now().date().isoformat(), slot, title.strip())
    await coordinator.async_request_refresh()
    return saved


async def settle_debts(coordinator: CompraHubCoordinator, *, group: str, person: str) -> int:
    """Marca como pagado todo lo pendiente entre tu cuenta y «person» en el grupo (en los dos sentidos)."""
    gid = _group(coordinator, group)
    if gid is None:
        raise ServiceValidationError("Falta el grupo.")
    me = coordinator.data.profile["id"]
    other = _member(coordinator, gid, person)["userId"]
    if other == me:
        raise ServiceValidationError("No puedes saldar deudas contigo.")
    count = 0
    for e in await coordinator.api.group_expenses(gid):
        for s in e.get("shares", []):
            pending = not s["settled"]
            if pending and (
                (e["paidBy"] == me and s["userId"] == other) or (e["paidBy"] == other and s["userId"] == me)
            ):
                await coordinator.api.set_share_settled(gid, e["id"], s["userId"], True)
                count += 1
    await coordinator.async_request_refresh()
    return count


def euros(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


def check_writable(coordinator: CompraHubCoordinator) -> None:
    if coordinator.data is None:
        raise HomeAssistantError("El hub aún no ha respondido; inténtalo en unos segundos.")
