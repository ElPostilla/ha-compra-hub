"""Acciones de Home Assistant: apuntar gastos, planificar comidas, saldar deudas."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
import homeassistant.helpers.config_validation as cv

from . import actions
from .const import CATEGORIES, DOMAIN, MEAL_SLOTS

ATTR_ENTRY = "config_entry_id"

ADD_EXPENSE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Required("description"): cv.string,
        vol.Required("amount"): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
        vol.Optional("category"): vol.In(CATEGORIES),
        vol.Optional("date"): cv.date,
        vol.Optional("group"): cv.string,
        vol.Optional("paid_by"): cv.string,
        vol.Optional("participants"): vol.All(cv.ensure_list, [cv.string]),
    }
)
PLAN_MEAL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Required("title"): cv.string,
        vol.Required("slot"): vol.In(MEAL_SLOTS),
        vol.Optional("date"): cv.date,
        vol.Optional("group"): cv.string,
    }
)
SETTLE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Required("group"): cv.string,
        vol.Required("person"): cv.string,
    }
)


def _coordinator(hass: HomeAssistant, call: ServiceCall):
    return actions.resolve_coordinator(hass, call.data.get(ATTR_ENTRY), call.context.user_id)


def async_register_services(hass: HomeAssistant) -> None:
    async def add_expense(call: ServiceCall) -> ServiceResponse:
        d = call.data
        saved = await actions.add_expense(
            _coordinator(hass, call),
            description=d["description"],
            amount=d["amount"],
            category=d.get("category"),
            date=d["date"].isoformat() if d.get("date") else None,
            group=d.get("group"),
            paid_by=d.get("paid_by"),
            participants=d.get("participants"),
        )
        return {"id": saved["id"], "amount": saved["amountCents"] / 100, "group": saved["group"]}

    async def plan_meal(call: ServiceCall) -> ServiceResponse:
        d = call.data
        saved = await actions.plan_meal(
            _coordinator(hass, call),
            title=d["title"],
            slot=d["slot"],
            date=d["date"].isoformat() if d.get("date") else None,
            group=d.get("group"),
        )
        return {"date": saved.get("date"), "slot": saved.get("slot"), "title": saved.get("title")}

    async def settle_debts(call: ServiceCall) -> ServiceResponse:
        count = await actions.settle_debts(
            _coordinator(hass, call), group=call.data["group"], person=call.data["person"]
        )
        return {"settled": count}

    hass.services.async_register(DOMAIN, "add_expense", add_expense, ADD_EXPENSE_SCHEMA, SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "plan_meal", plan_meal, PLAN_MEAL_SCHEMA, SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "settle_debts", settle_debts, SETTLE_SCHEMA, SupportsResponse.OPTIONAL)
