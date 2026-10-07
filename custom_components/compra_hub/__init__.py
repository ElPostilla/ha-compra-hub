"""Integración de Home Assistant para el hub familiar compra.raspimc.org."""

from __future__ import annotations

import aiohttp

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    OAuth2TokenRequestError,
    OAuth2TokenRequestReauthError,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    ImplementationUnavailableError,
    OAuth2Session,
    async_get_config_entry_implementation,
)
from homeassistant.loader import async_get_integration

from .api import HubApi
from .const import CONF_HUB, CONF_PANEL
from .coordinator import CompraHubConfigEntry, CompraHubCoordinator
from .oauth import async_ensure_implementation
from .panel import async_add_panel, async_remove_panel

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR, Platform.TODO]


async def async_setup_entry(hass: HomeAssistant, entry: CompraHubConfigEntry) -> bool:
    """Prepara la sesión OAuth2 y la primera lectura del hub."""
    await async_ensure_implementation(hass)
    try:
        implementation = await async_get_config_entry_implementation(hass, entry)
    except ImplementationUnavailableError as err:
        raise ConfigEntryNotReady(str(err)) from err
    session = OAuth2Session(hass, entry, implementation)
    try:
        await session.async_ensure_token_valid()
    except OAuth2TokenRequestReauthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (aiohttp.ClientError, OAuth2TokenRequestError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    api = HubApi(async_get_clientsession(hass), entry.data[CONF_HUB], oauth=session)
    coordinator = CompraHubCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if entry.options.get(CONF_PANEL, True):
        integration = await async_get_integration(hass, entry.domain)
        await async_add_panel(hass, entry.entry_id, entry.data[CONF_HUB], str(integration.version))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: CompraHubConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CompraHubConfigEntry) -> bool:
    """Descarga las plataformas y, si era la última cuenta de ese hub, el panel."""
    async_remove_panel(hass, entry.entry_id, entry.data[CONF_HUB])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
