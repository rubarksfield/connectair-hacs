"""Reserve optional actions until a boost confirmation register is verified."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

if TYPE_CHECKING:
    from . import ConnectairConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConnectairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Do not expose an action that cannot yet confirm its device response."""
