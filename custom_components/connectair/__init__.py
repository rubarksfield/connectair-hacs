"""S&P Connectair cloud integration."""

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import ConnectairCoordinator

    type ConnectairConfigEntry = ConfigEntry[ConnectairCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ConnectairConfigEntry) -> bool:
    """Authenticate, fetch real devices and then expose entities."""
    from homeassistant.exceptions import ConfigEntryAuthFailed
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import ConnectairClient
    from .auth import Auth0Session
    from .const import CONF_TOKENS, PLATFORMS
    from .coordinator import ConnectairCoordinator
    from .models import AuthenticationError

    async def save_tokens(tokens: dict) -> None:
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKENS: tokens})

    session = async_get_clientsession(hass)
    tokens = entry.data.get(CONF_TOKENS)
    if not isinstance(tokens, Mapping):
        raise ConfigEntryAuthFailed("Connectair credentials need to be renewed")
    try:
        auth = Auth0Session(session, tokens, save_tokens=save_tokens)
    except AuthenticationError, TypeError, ValueError, OverflowError:
        raise ConfigEntryAuthFailed("Connectair credentials need to be renewed") from None
    client = ConnectairClient(session, auth.async_get_access_token)
    coordinator = ConnectairCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConnectairConfigEntry) -> bool:
    """Unload entity platforms; HA owns the shared HTTP session."""
    from .const import PLATFORMS

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
