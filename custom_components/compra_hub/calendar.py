"""Recordatorios del calendario del hub como calendarios de HA.

Se pueden crear, cambiar y borrar desde Home Assistant. Un recordatorio del
hub es un día (y opcionalmente una hora) con un texto. No tiene duración ni
fin, así que los que tienen hora se muestran como eventos de una hora.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import PERSONAL
from .coordinator import CompraHubConfigEntry, CompraHubCoordinator
from .entity import CompraHubEntity

PARALLEL_UPDATES = 0
TIMED_DURATION = timedelta(hours=1)
# Repeticiones que entiende el hub, en formato RRULE de iCalendar.
RRULE_TO_RECURRENCE = {"FREQ=DAILY": "daily", "FREQ=WEEKLY": "weekly", "FREQ=MONTHLY": "monthly"}
RECURRENCE_TO_RRULE = {v: k for k, v in RRULE_TO_RECURRENCE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CompraHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(NotesCalendar(coordinator, scope) for scope in coordinator.data.notes)


def _recurrence(rrule: str | None) -> str:
    if not rrule:
        return "none"
    key = ";".join(p for p in rrule.upper().split(";") if p.startswith("FREQ="))
    if key not in RRULE_TO_RECURRENCE or rrule.upper() not in (key, f"{key};INTERVAL=1"):
        raise HomeAssistantError(
            "El hub solo admite recordatorios que se repiten cada día, cada semana o cada mes."
        )
    return RRULE_TO_RECURRENCE[key]


def _day_and_time(dtstart: date | datetime) -> tuple[str, str | None]:
    if isinstance(dtstart, datetime):
        local = dt_util.as_local(dtstart)
        return local.date().isoformat(), local.strftime("%H:%M")
    return dtstart.isoformat(), None


class NotesCalendar(CompraHubEntity, CalendarEntity):
    """Recordatorios personales o de un grupo.

    El hub ya devuelve los recordatorios repetidos proyectados un año hacia
    atrás y otro hacia delante. Aquí solo se convierten; el original de una
    serie (origin) es el que lleva la repetición.
    """

    _attr_icon = "mdi:calendar-heart"
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
    )

    def __init__(self, coordinator: CompraHubCoordinator, scope: str) -> None:
        super().__init__(coordinator, "calendario", f"calendario:{scope}")
        self._scope = scope
        self._group_id = None if scope == PERSONAL else scope
        self._attr_name = self.group_name(self._group_id)

    @property
    def available(self) -> bool:
        return super().available and self._scope in self.coordinator.data.notes

    def _entries(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (day, e)
            for day, entries in self.coordinator.data.notes.get(self._scope, {}).items()
            for e in entries
        ]

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        tz = dt_util.get_default_time_zone()
        for day, e in self._entries():
            d = date.fromisoformat(day)
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
                    uid=e["id"],
                    recurrence_id=None if e.get("origin", True) else day,
                    rrule=RECURRENCE_TO_RRULE.get(e.get("recurrence") or "none")
                    if e.get("origin", True)
                    else None,
                )
            )
        events.sort(key=lambda ev: ev.start_datetime_local)
        return events

    def _original(self, note_id: str) -> tuple[str, dict[str, Any]]:
        for day, e in self._entries():
            if e["id"] == note_id and e.get("origin", True):
                return day, e
        raise HomeAssistantError("Ese recordatorio ya no existe en el hub.")

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

    async def async_create_event(self, **kwargs: Any) -> None:
        day, time = _day_and_time(kwargs["dtstart"])
        await self.coordinator.api.add_note(
            self._group_id,
            {
                "date": day,
                "note": kwargs["summary"],
                "time": time,
                "recurrence": _recurrence(kwargs.get("rrule")),
            },
        )
        await self.coordinator.async_refresh()

    async def async_delete_event(
        self, uid: str, recurrence_id: str | None = None, recurrence_range: str | None = None
    ) -> None:
        # El hub no tiene excepciones dentro de una serie: borrar una
        # repetición borra el recordatorio entero.
        await self.coordinator.api.delete_note(self._group_id, uid)
        await self.coordinator.async_refresh()

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        old_day, old = self._original(uid)
        day, time = _day_and_time(event["dtstart"])
        body = {
            "note": event.get("summary") or old["note"],
            "time": time,
            "recurrence": _recurrence(event.get("rrule")),
            # Lo que HA no conoce se conserva: importancia y aviso.
            "importance": old.get("importance") or "media",
            "remindMinutes": old.get("remindMinutes"),
        }
        if day == old_day or recurrence_id:
            await self.coordinator.api.update_note(self._group_id, uid, body)
        else:
            # El hub no cambia la fecha de un recordatorio: se crea en el día
            # nuevo con los mismos datos y se borra el antiguo.
            await self.coordinator.api.add_note(self._group_id, {"date": day, **body})
            await self.coordinator.api.delete_note(self._group_id, uid)
        await self.coordinator.async_refresh()
