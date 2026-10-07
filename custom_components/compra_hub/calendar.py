"""Recordatorios del calendario del hub como calendarios de HA (solo lectura)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import PERSONAL
from .coordinator import CompraHubConfigEntry, CompraHubCoordinator
from .entity import CompraHubEntity

PARALLEL_UPDATES = 0
# Un recordatorio con hora no tiene duración en el hub: se muestra como un
# evento de una hora.
TIMED_DURATION = timedelta(hours=1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CompraHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(NotesCalendar(coordinator, scope) for scope in coordinator.data.notes)


class NotesCalendar(CompraHubEntity, CalendarEntity):
    """Recordatorios personales o de un grupo.

    El hub ya devuelve los recordatorios repetidos proyectados un año hacia
    atrás y otro hacia delante, así que aquí solo se convierten.
    """

    _attr_icon = "mdi:calendar-heart"

    def __init__(self, coordinator: CompraHubCoordinator, scope: str) -> None:
        super().__init__(coordinator, "calendario", f"calendario:{scope}")
        self._scope = scope
        self._attr_name = self.group_name(None if scope == PERSONAL else scope)

    @property
    def available(self) -> bool:
        return super().available and self._scope in self.coordinator.data.notes

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        tz = dt_util.get_default_time_zone()
        for day, entries in self.coordinator.data.notes.get(self._scope, {}).items():
            d = date.fromisoformat(day)
            for e in entries:
                if e.get("time"):
                    hh, mm = (int(x) for x in e["time"].split(":")[:2])
                    start: date | datetime = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
                    end: date | datetime = start + TIMED_DURATION
                else:
                    start, end = d, d + timedelta(days=1)
                events.append(
                    CalendarEvent(
                        start=start,
                        end=end,
                        summary=e["note"],
                        uid=f"{e['id']}:{day}",
                        rrule=None,
                    )
                )
        events.sort(key=lambda ev: ev.start_datetime_local)
        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        return next((ev for ev in self._events() if ev.end_datetime_local > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            ev
            for ev in self._events()
            if ev.end_datetime_local > start_date and ev.start_datetime_local < end_date
        ]
