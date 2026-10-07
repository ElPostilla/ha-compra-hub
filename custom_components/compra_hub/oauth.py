"""Registro de la implementación OAuth2 (cliente público + PKCE)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import AUTHORIZE_URL, CLIENT_ID, DOMAIN, SCOPES, TOKEN_URL


class CompraHubImplementation(config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce):
    """Keycloak del hub con los scopes que necesita la integración."""

    @property
    def name(self) -> str:
        return "Cuenta de compra.raspimc.org"

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {"scope": SCOPES}
        data.update(super().extra_authorize_data)
        return data


async def async_ensure_implementation(hass: HomeAssistant) -> None:
    """Registra la implementación una sola vez.

    Volver a registrarla crearía otro code_verifier de PKCE y rompería un
    inicio de sesión que estuviera a medias.
    """
    implementations = await config_entry_oauth2_flow.async_get_implementations(hass, DOMAIN)
    if DOMAIN in implementations:
        return
    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        CompraHubImplementation(hass, DOMAIN, CLIENT_ID, AUTHORIZE_URL, TOKEN_URL),
    )
