"""Flujo de configuración: elegir el hub e iniciar sesión con Keycloak."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HubApi, HubAuthError, HubError
from .const import CONF_HA_USER, CONF_HUB, CONF_PANEL, DEFAULT_HUB, DOMAIN, HUBS, LOGGER
from .oauth import async_ensure_implementation


class CompraHubFlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Conecta Home Assistant con una cuenta del hub."""

    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._hub: str = DEFAULT_HUB

    @property
    def logger(self) -> logging.Logger:
        return LOGGER

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CompraHubOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {vol.Required(CONF_HUB, default=DEFAULT_HUB): vol.In(HUBS)}
                ),
            )
        self._hub = user_input[CONF_HUB]
        await async_ensure_implementation(self.hass)
        return await self.async_step_pick_implementation()

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._hub = entry_data[CONF_HUB]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders={"hub": self._hub},
            )
        await async_ensure_implementation(self.hass)
        return await self.async_step_pick_implementation()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        api = HubApi(
            async_get_clientsession(self.hass), self._hub, token=data["token"]["access_token"]
        )
        try:
            profile = await api.profile()
        except HubAuthError:
            return self.async_abort(reason="oauth_unauthorized")
        except HubError:
            LOGGER.exception("No se pudo leer el perfil del hub")
            return self.async_abort(reason="cannot_connect")

        # Un mismo usuario puede conectar producción y dev a la vez.
        await self.async_set_unique_id(f"{self._hub}:{profile['id']}")
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data={**data, CONF_HUB: self._hub}
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"@{profile['username']} · {self._hub}",
            data={**data, CONF_HUB: self._hub},
        )


NO_USER = "-"


class CompraHubOptionsFlow(OptionsFlow):
    """Opciones: panel en la barra lateral y usuario de HA al que pertenece la cuenta."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data = dict(user_input)
            if data.get(CONF_HA_USER) == NO_USER:
                data.pop(CONF_HA_USER)
            return self.async_create_entry(data=data)
        users = {NO_USER: "Nadie en concreto"}
        users.update(
            {
                u.id: u.name or u.id
                for u in await self.hass.auth.async_get_users()
                if not u.system_generated and u.is_active
            }
        )
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PANEL, default=options.get(CONF_PANEL, True)): bool,
                    vol.Required(CONF_HA_USER, default=options.get(CONF_HA_USER, NO_USER)): vol.In(users),
                }
            ),
        )
