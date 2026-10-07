"""Sensores: saldo en cada grupo, gasto del mes y menú de hoy."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MEAL_SLOTS, PERSONAL
from .coordinator import CompraHubConfigEntry, CompraHubCoordinator
from .entity import CompraHubEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CompraHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [MonthSpentSensor(coordinator)]
    entities += [BalanceSensor(coordinator, gid) for gid in coordinator.data.groups]
    entities += [
        MealSensor(coordinator, scope, slot)
        for scope in coordinator.data.meals
        for slot in MEAL_SLOTS
    ]
    async_add_entities(entities)


class MonthSpentSensor(CompraHubEntity, SensorEntity):
    """Total de tus gastos personales en el mes en curso."""

    _attr_name = "Este mes"
    _attr_icon = "mdi:cash-multiple"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: CompraHubCoordinator) -> None:
        super().__init__(coordinator, "gastos", "gastado_mes")

    @property
    def native_value(self) -> float:
        return self.coordinator.data.month_spent_cents / 100


class BalanceSensor(CompraHubEntity, SensorEntity):
    """Tu saldo en un grupo: positivo, te deben; negativo, debes."""

    _attr_icon = "mdi:scale-balance"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: CompraHubCoordinator, group_id: str) -> None:
        super().__init__(coordinator, "gastos", f"saldo:{group_id}")
        self._group_id = group_id
        self._attr_name = f"Saldo {self.group_name(group_id)}"

    @property
    def available(self) -> bool:
        return super().available and self._group_id in self.coordinator.data.groups

    @property
    def native_value(self) -> float:
        return self.coordinator.data.balances.get(self._group_id, 0) / 100

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        cents = self.coordinator.data.balances.get(self._group_id, 0)
        return {"situacion": "te deben" if cents > 0 else "debes" if cents < 0 else "saldado"}


class MealSensor(CompraHubEntity, SensorEntity):
    """Lo que hay planificado hoy para comer o cenar."""

    def __init__(self, coordinator: CompraHubCoordinator, scope: str, slot: str) -> None:
        super().__init__(coordinator, "menu", f"menu:{scope}:{slot}")
        self._scope = scope
        self._slot = slot
        group = self.group_name(None if scope == PERSONAL else scope)
        label = "Comida de hoy" if slot == "comida" else "Cena de hoy"
        self._attr_name = f"{label} {group}" if group else label
        self._attr_icon = "mdi:silverware-fork-knife" if slot == "comida" else "mdi:food-variant"

    @property
    def available(self) -> bool:
        return super().available and self._scope in self.coordinator.data.meals

    @property
    def native_value(self) -> str:
        return self.coordinator.data.meals.get(self._scope, {}).get(self._slot) or "Sin planificar"
