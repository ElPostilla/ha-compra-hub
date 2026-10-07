"""Entidad base.

Un dispositivo de servicio por app del hub («Compra», «Tareas»,
«Calendario», «Gastos», «Menú») y cuenta. HA 2026 antepone siempre el
nombre del dispositivo al de la entidad, así que la lista personal, sin
nombre propio, se llama solo «Compra» y la de un grupo «Compra Casa». Son
los nombres que usa Assist: «añade leche a la lista compra casa».
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEV_HUBS, CONF_HUB, DOMAIN
from .coordinator import CompraHubCoordinator

APPS = {
    "compra": ("Compra", "lista"),
    "tareas": ("Tareas", "todo"),
    "calendario": ("Calendario", "calendario"),
    "gastos": ("Gastos", "gastos"),
    "menu": ("Menú", "menu"),
}


class CompraHubEntity(CoordinatorEntity[CompraHubCoordinator]):
    """Base común."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CompraHubCoordinator, app: str, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        hub = entry.data[CONF_HUB]
        label, path = APPS[app]
        if hub in CONF_DEV_HUBS:
            label = f"{label} dev"  # sin paréntesis: Assist no los casa
        self._attr_unique_id = f"{entry.unique_id}:{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.unique_id}:{app}")},
            name=label,
            manufacturer="raspimc.org",
            model=f"{hub} · @{coordinator.data.profile['username']}",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://{hub}/{path}/",
        )

    def group_name(self, group_id: str | None) -> str | None:
        return self.coordinator.data.groups.get(group_id) if group_id else None
