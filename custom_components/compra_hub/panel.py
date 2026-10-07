"""Panel de la barra lateral con el hub dentro.

Un panel por hub (no por cuenta): si hay dos cuentas del mismo hub, se
comparte. Se quita al descargar la última entrada de ese hub. El hub se
muestra en un iframe; la sesión es la del propio hub (cookie), así que
dentro solo funciona si Home Assistant está en el mismo dominio que el hub
(*.raspimc.org) y Keycloak permite mostrarse dentro de esa dirección. Por
eso el panel lleva siempre «Abrir en una ventana».
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import CONF_DEV_HUBS, DOMAIN

STATIC_URL = "/compra_hub_static"
WWW = Path(__file__).parent / "www"


def _fingerprint(name: str) -> str:
    """Huella del contenido: Home Assistant sirve estos ficheros sin
    Cache-Control y el navegador puede seguir usando una copia vieja si la URL
    no cambia (pasó con la 0.3.0: la tarjeta corregida no llegaba)."""
    return hashlib.sha256((WWW / name).read_bytes()).hexdigest()[:12]
DATA_STATIC = f"{DOMAIN}_static_registered"
DATA_PANELS = f"{DOMAIN}_panels"  # frontend_url_path -> ids de entrada


def _panel_path(hub: str) -> str:
    return "compra-hub-dev" if hub in CONF_DEV_HUBS else "compra-hub"


async def async_register_frontend(hass: HomeAssistant, version: str) -> None:
    """Ficheros del panel y de la tarjeta; la tarjeta se carga en todos los paneles.

    Una vez por ejecución de Home Assistant: las rutas estáticas no se
    pueden registrar dos veces.
    """
    if hass.data.get(DATA_STATIC):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(WWW), cache_headers=False)]
    )
    card = await hass.async_add_executor_job(_fingerprint, "card.js")
    frontend.add_extra_js_url(hass, f"{STATIC_URL}/card.js?v={card}")
    hass.data[DATA_STATIC] = True


async def async_add_panel(hass: HomeAssistant, entry_id: str, hub: str, version: str) -> None:
    path = _panel_path(hub)
    users = hass.data.setdefault(DATA_PANELS, {}).setdefault(path, set())
    if not users:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=path,
            webcomponent_name="compra-hub-panel",
            sidebar_title="Compra Hub dev" if hub in CONF_DEV_HUBS else "Compra Hub",
            sidebar_icon="mdi:basket-outline",
            module_url=f"{STATIC_URL}/panel.js?v={await hass.async_add_executor_job(_fingerprint, 'panel.js')}",
            config={"url": f"https://{hub}/", "hub": hub},
            require_admin=False,
        )
    users.add(entry_id)


def async_remove_panel(hass: HomeAssistant, entry_id: str, hub: str) -> None:
    path = _panel_path(hub)
    users = hass.data.get(DATA_PANELS, {}).get(path)
    if not users:
        return
    users.discard(entry_id)
    if not users:
        frontend.async_remove_panel(hass, path, warn_if_unknown=False)
