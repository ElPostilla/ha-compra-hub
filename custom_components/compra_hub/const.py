"""Constantes de la integración Compra Hub."""

from datetime import timedelta
import logging

DOMAIN = "compra_hub"
LOGGER = logging.getLogger(__package__)

# Cliente público del realm "compras" en Keycloak (PKCE, sin secreto). El
# mismo realm sirve producción y dev: solo cambia la URL del hub.
CLIENT_ID = "home-assistant"
OIDC_BASE = "https://keycloak.raspimc.org/realms/compras/protocol/openid-connect"
AUTHORIZE_URL = f"{OIDC_BASE}/auth"
TOKEN_URL = f"{OIDC_BASE}/token"
# offline_access: el refresh token no caduca con la sesión del navegador
# (24 h en el realm), sino tras 30 días sin usarse -- HA lo usa cada pocos
# minutos, así que no hay que volver a iniciar sesión.
SCOPES = "openid offline_access"

CONF_HUB = "hub"
HUBS = {
    "compra.raspimc.org": "compra.raspimc.org",
    "compra-dev.raspimc.org": "compra-dev.raspimc.org (pruebas)",
}
DEFAULT_HUB = "compra.raspimc.org"
# Sus dispositivos llevan «dev» («Compra dev») para no confundirlos con los de producción.
CONF_DEV_HUBS = {"compra-dev.raspimc.org"}

UPDATE_INTERVAL = timedelta(seconds=60)

PERSONAL = "personal"
MEAL_SLOTS = ("comida", "cena")
