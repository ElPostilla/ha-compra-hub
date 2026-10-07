"""Frases propias para Assist (el agente de conversación de Home Assistant).

Se registran como «disparadores» del agente por defecto, igual que las
automatizaciones con disparador de conversación, y responden con texto.
Usan la cuenta del usuario de Home Assistant que habla (ver
actions.resolve_coordinator).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
import re
from typing import Any

from homeassistant.components.conversation import ConversationInput
from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from . import actions
from .const import CATEGORIES, LOGGER

Q = "(qué|que)"
HOW_MUCH = "(cuánto|cuanto)"
EUROS = "[euros|euro|€|eur]"
GROUP = "[el] [grupo] {grupo}"

# --------------------------------------------------------------- números

UNITS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciséis": 16, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintiún": 21, "veintiun": 21, "veintidós": 22, "veintidos": 22,
    "veintitrés": 23, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiséis": 26,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90}
HUNDREDS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400,
    "quinientos": 500, "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}


def _words_to_int(words: list[str]) -> int | None:
    total, seen = 0, False
    for w in words:
        if w == "y":
            continue
        if w in HUNDREDS:
            total += HUNDREDS[w]
        elif w in TENS:
            total += TENS[w]
        elif w in UNITS:
            total += UNITS[w]
        elif w == "mil":
            total = max(total, 1) * 1000
        elif w.isdigit():
            total += int(w)
        else:
            return None
        seen = True
    return total if seen else None


def parse_amount(text: str) -> float | None:
    """«20», «20,50», «20.5», «20 con 50», «veinte euros con cincuenta» -> euros."""
    t = text.lower().replace("€", " ").strip()
    t = re.sub(r"\b(euros?|eur|céntimos?|centimos?)\b", " ", t)
    m = re.fullmatch(r"\s*(\d+)(?:[.,](\d{1,2}))?\s*", t)
    if m:
        cents = int((m.group(2) or "0").ljust(2, "0"))
        return int(m.group(1)) + cents / 100
    parts = re.split(r"\bcon\b", t)
    if len(parts) > 2:
        return None
    whole = _words_to_int(parts[0].split())
    if whole is None:
        return None
    cents = _words_to_int(parts[1].split()) if len(parts) == 2 else 0
    if cents is None or cents > 99:
        return None
    return whole + cents / 100


def _clean_concept(text: str) -> str:
    """«el súper» -> «Súper»: sin artículo delante y con mayúscula."""
    t = re.sub(r"^(el|la|los|las|un|una|unos|unas)\s+", "", text.strip(), flags=re.IGNORECASE)
    return t[:1].upper() + t[1:] if t else "Gasto"


def _guess_category(concept: str) -> str:
    c = concept.lower()
    rules = {
        "comida": ("súper", "super", "mercadona", "dia", "lidl", "carrefour", "pan", "fruta", "comida",
                   "compra", "restaurante", "cena", "pizza", "bar"),
        "transporte": ("gasolina", "taxi", "bus", "autobús", "tren", "metro", "parking", "peaje", "uber"),
        "casa": ("luz", "agua", "gas", "alquiler", "internet", "comunidad", "ikea", "limpieza"),
        "salud": ("farmacia", "médico", "medico", "dentista", "medicinas", "gafas"),
        "ocio": ("cine", "concierto", "regalo", "viaje", "netflix", "spotify", "libro", "juego"),
    }
    for cat, words in rules.items():
        if any(w in c for w in words):
            return cat
    return "otros"


# ------------------------------------------------------------- respuestas

def _slot(result: Any, name: str) -> str | None:
    ent = result.entities.get(name)
    if ent is None:
        return None
    value = ent.value if isinstance(ent.value, str) else ent.text
    return str(value).strip() or None


def _coordinator(hass: HomeAssistant, user_input: ConversationInput):
    return actions.resolve_coordinator(hass, None, user_input.context.user_id)


async def _expense(hass, user_input, result, *, group: bool) -> str:
    raw = _slot(result, "importe") or ""
    amount = parse_amount(raw)
    if amount is None:
        return f"No he entendido el importe «{raw}». Dímelo en cifras, por ejemplo: apunta un gasto de 12,50 euros en el súper."
    concept = _clean_concept(_slot(result, "concepto") or "")
    saved = await actions.add_expense(
        _coordinator(hass, user_input),
        description=concept,
        amount=amount,
        category=_guess_category(concept),
        group=_slot(result, "grupo") if group else None,
    )
    where = f" en {saved['group']}, a partes iguales entre todos" if saved["group"] else ""
    return f"Apuntado: {actions.euros(saved['amountCents'])} en «{concept}»{where}."


def _meal_lines(coordinator, meals_by_scope: dict[str | None, list[dict[str, Any]]], slot: str) -> list[str]:
    lines = []
    for scope, meals in meals_by_scope.items():
        for m in meals:
            if m["slot"] == slot and m.get("title"):
                name = coordinator.data.groups.get(scope) if scope else None
                lines.append(f"{m['title']}{f' ({name})' if name else ''}")
    return lines


async def _menu(hass, user_input, result, *, slot: str, tomorrow: bool) -> str:
    coordinator = _coordinator(hass, user_input)
    day = dt_util.now().date() + timedelta(days=1 if tomorrow else 0)
    iso = day.isoformat()
    scopes: list[str | None] = [None, *coordinator.data.groups]
    meals = {s: await coordinator.api.meals(s, iso, iso) for s in scopes}
    when = "mañana" if tomorrow else "hoy"
    what = "comer" if slot == "comida" else "cenar"
    lines = _meal_lines(coordinator, meals, slot)
    if not lines:
        return f"No hay nada planificado para {what} {when}."
    return f"Para {what} {when}: " + "; ".join(lines) + "."


async def _plan(hass, user_input, result, *, slot: str, tomorrow: bool, group: bool) -> str:
    dish = _clean_concept(_slot(result, "plato") or "")
    day = dt_util.now().date() + timedelta(days=1 if tomorrow else 0)
    await actions.plan_meal(
        _coordinator(hass, user_input),
        title=dish,
        slot=slot,
        date=day.isoformat(),
        group=_slot(result, "grupo") if group else None,
    )
    what = "comer" if slot == "comida" else "cenar"
    return f"Hecho: {dish.lower()} para {what} {'mañana' if tomorrow else 'hoy'}."


async def _fresh(hass, user_input):
    """Cuenta con datos recién pedidos: una pregunta justo después de apuntar
    algo no puede responder con el sondeo de hace un minuto."""
    coordinator = _coordinator(hass, user_input)
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise HomeAssistantError("No he podido hablar con el hub. Inténtalo de nuevo en un momento.")
    return coordinator


async def _balances(hass, user_input, result, *, mode: str) -> str:
    coordinator = await _fresh(hass, user_input)
    data = coordinator.data
    gid = None
    if (name := _slot(result, "grupo")) is not None:
        gid = data.find_group(name)
        if gid is None:
            return f"No encuentro el grupo «{name}»."
    groups = [gid] if gid else list(data.groups)
    if not groups:
        return "No tienes grupos con gastos compartidos."
    if mode == "who":
        out = []
        for g in groups:
            for d in data.debts.get(g, []):
                out.append(f"{d['fromUsername']} debe {actions.euros(d['amountCents'])} a {d['toUsername']}")
        where = f" en {data.groups[gid]}" if gid else ""
        return ("Quién debe a quién" + where + ": " + "; ".join(out) + ".") if out else f"Todo saldado{where}."
    parts = []
    for g in groups:
        cents = data.balances.get(g, 0)
        if mode == "owe" and cents < 0:
            parts.append(f"debes {actions.euros(-cents)} en {data.groups[g]}")
        elif mode == "owed" and cents > 0:
            parts.append(f"te deben {actions.euros(cents)} en {data.groups[g]}")
    if not parts:
        return "No debes nada." if mode == "owe" else "No te deben nada."
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "."


async def _month(hass, user_input, result) -> str:
    coordinator = await _fresh(hass, user_input)
    return f"Este mes llevas gastados {actions.euros(coordinator.data.month_spent_cents)} en gastos personales."


async def _settle(hass, user_input, result) -> str:
    person = _slot(result, "persona") or ""
    group = _slot(result, "grupo") or ""
    n = await actions.settle_debts(_coordinator(hass, user_input), group=group, person=person)
    if not n:
        return f"No había nada pendiente entre tú y {person} en {group}."
    parts = "1 parte pendiente" if n == 1 else f"{n} partes pendientes"
    return f"Hecho: marcado como pagado ({parts}) entre tú y {person}."


# ---------------------------------------------------------------- frases

Handler = Callable[[HomeAssistant, ConversationInput, Any], Awaitable[str]]


def _triggers() -> list[tuple[list[str], Handler]]:
    from functools import partial as p

    add = "(apunta|apúntame|anota|anótame|añade|registra)"
    meal_words = {"comida": ("comer", "comida"), "cena": ("cenar", "cena")}
    out: list[tuple[list[str], Handler]] = [
        (
            [
                f"{add} (en|a) {GROUP} [un] gasto de {{importe}} {EUROS} (en|de|por|para) {{concepto}}",
                f"{add} [un] gasto de {{importe}} {EUROS} (en|de|por|para) {{concepto}} en {GROUP}",
            ],
            p(_expense, group=True),
        ),
        (
            [
                f"{add} [un] gasto de {{importe}} {EUROS} (en|de|por|para) {{concepto}}",
                f"(he gastado|gasté|me he gastado) {{importe}} {EUROS} (en|de) {{concepto}}",
            ],
            p(_expense, group=False),
        ),
        ([f"{HOW_MUCH} (he gastado|llevo gastado|gasto llevo|gasté) este mes"], _month),
        ([f"{HOW_MUCH} debo en {GROUP}", f"{HOW_MUCH} debo"], p(_balances, mode="owe")),
        (
            [f"{HOW_MUCH} me deben en {GROUP}", f"{HOW_MUCH} me deben", "(quién|quien) me debe [dinero]"],
            p(_balances, mode="owed"),
        ),
        (
            [
                "(quién|quien) debe a (quién|quien) en {grupo}",
                "(quién|quien) debe a (quién|quien)",
                "(cómo|como) (van|están|estan) las cuentas (en|de) {grupo}",
            ],
            p(_balances, mode="who"),
        ),
        (
            [
                "[ya] he pagado a {persona} en {grupo}",
                "{persona} ya me ha pagado en {grupo}",
                "salda las deudas con {persona} en {grupo}",
            ],
            _settle,
        ),
    ]
    for slot, (verb, noun) in meal_words.items():
        we = "comemos" if slot == "comida" else "cenamos"
        me = "como" if slot == "comida" else "ceno"
        out.append(
            ([f"{Q} hay (de|para) ({verb}|{noun}) [hoy]", f"{Q} ({we}|{me}) hoy"], p(_menu, slot=slot, tomorrow=False))
        )
        out.append(
            ([f"{Q} hay (de|para) ({verb}|{noun}) mañana", f"{Q} ({we}|{me}) mañana"], p(_menu, slot=slot, tomorrow=True))
        )
        for tomorrow, word in ((False, "hoy"), (True, "mañana")):
            out.append(
                (
                    [f"(pon|planifica|apunta) {{plato}} (para|de) {verb} {word} en {GROUP}"],
                    p(_plan, slot=slot, tomorrow=tomorrow, group=True),
                )
            )
            out.append(
                (
                    [f"(pon|planifica|apunta) {{plato}} (para|de) {verb} {word}"],
                    p(_plan, slot=slot, tomorrow=tomorrow, group=False),
                )
            )
    return out


def async_register_voice(hass: HomeAssistant) -> list[CALLBACK_TYPE]:
    manager = get_agent_manager(hass)
    unregister: list[CALLBACK_TYPE] = []
    for sentences, handler in _triggers():

        async def _run(user_input: ConversationInput, result: Any, handler: Handler = handler) -> str:
            try:
                return await handler(hass, user_input, result)
            except HomeAssistantError as err:
                return str(err)
            except Exception:  # noqa: BLE001 - Assist debe responder algo siempre
                LOGGER.exception("Error atendiendo una frase de voz")
                return "No he podido hablar con el hub. Inténtalo de nuevo en un momento."

        unregister.append(manager.register_trigger(sentences, _run))
    return unregister
