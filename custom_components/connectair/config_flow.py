"""Auth0 PKCE callback relay with a verified renewable Connectair account."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorType

from .api import ConnectairClient
from .auth import Auth0Session, async_exchange_callback, create_authorization_request
from .const import CONF_CALLBACK_URL, CONF_TOKENS, DOMAIN
from .models import AuthenticationError, ConnectairError, TransportError


class ConnectairConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Authenticate at the existing provider-approved Connectair callback."""

    VERSION = 1

    def __init__(self) -> None:
        self._authorization_request = None
        self._pending_auth: Auth0Session | None = None
        self._pending_input: dict[str, Any] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_login("user", user_input)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start a new login, leaving the original account entry intact."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_login("reauth_confirm", user_input)

    async def _async_login(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if self._authorization_request is None:
            self._authorization_request = create_authorization_request()
        errors = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            if user_input != self._pending_input:
                self._pending_auth = None
                self._pending_input = None
            try:
                auth = self._pending_auth
                if auth is None:
                    if "access_token" in user_input:
                        # Also accepts a pre-exchanged bundle through HA's local flow API.
                        # Access tokens are not offered in the human-facing form.
                        tokens = {
                            key: user_input[key]
                            for key in ("access_token", "refresh_token", "expires_at")
                            if key in user_input
                        }
                    elif "refresh_token" in user_input and (
                        user_input["refresh_token"] or not user_input.get(CONF_CALLBACK_URL)
                    ):
                        refresh_token = user_input["refresh_token"]
                        if not isinstance(refresh_token, str) or not refresh_token.strip():
                            raise AuthenticationError("A private refresh token is required")
                        tokens = {
                            "access_token": "pending-refresh",
                            "refresh_token": refresh_token.strip(),
                            "expires_at": 0,
                        }
                    else:
                        tokens = await async_exchange_callback(
                            session, self._authorization_request, user_input[CONF_CALLBACK_URL]
                        )
                    if not tokens.get("refresh_token"):
                        errors["base"] = "missing_refresh_token"
                    else:
                        auth = Auth0Session(session, tokens)
                        # Retain renewal in flow memory before account verification:
                        # a transient outage must not lose a rotated refresh token.
                        await auth.async_get_access_token(force_refresh=True)
                        self._pending_auth = auth
                        self._pending_input = dict(user_input)
                if auth is not None:
                    client = ConnectairClient(session, auth.async_get_access_token)
                    account = await client.async_get_user()
                    account_id = account.get("id")
                    if not isinstance(account_id, (str, int)) or not str(account_id):
                        raise AuthenticationError("Account identity was not returned")
                    await self.async_set_unique_id(str(account_id))
                    data = {CONF_TOKENS: auth.tokens}
                    self._pending_auth = None
                    self._pending_input = None
                    if self.source == config_entries.SOURCE_REAUTH:
                        self._abort_if_unique_id_mismatch()
                        return self.async_update_reload_and_abort(
                            self._get_reauth_entry(), data=data
                        )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="Connectair", data=data)
            except AuthenticationError:
                self._pending_auth = None
                self._pending_input = None
                errors["base"] = "invalid_auth"
            except TransportError:
                errors["base"] = "cannot_connect"
            except ConnectairError:
                errors["base"] = "invalid_response"
            except KeyError, TypeError, ValueError:
                self._pending_auth = None
                self._pending_input = None
                errors["base"] = "invalid_auth"
        return self.async_show_form(
            step_id=step_id,
            # HA's REST flow creation does not forward initial input. Allow a
            # token bundle through configure. Declare an optional masked refresh
            # field so clients which filter undeclared fields can also enroll.
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CALLBACK_URL): str,
                    vol.Optional("refresh_token"): TextSelector(
                        {"type": TextSelectorType.PASSWORD, "autocomplete": "off"}
                    ),
                },
                extra=vol.ALLOW_EXTRA,
            ),
            errors=errors,
            description_placeholders={
                "authorization_url": self._authorization_request.authorization_url
            },
        )
