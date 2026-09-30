"""Native four-speed fans backed by confirmed S&P device registers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ConnectairCoordinator, ConnectairEntity, async_add_device_entities

if TYPE_CHECKING:
    from . import ConnectairConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConnectairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create native fans for the discovered units."""
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda c, d: [ConnectairFan(c, d)],
        require_supported_state=True,
    )


class ConnectairFan(ConnectairEntity, FanEntity):
    """Set a speed, allowing the API to select manual mode when necessary."""

    _attr_name = None
    _attr_icon = "mdi:fan"
    _attr_speed_count = 4
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON

    def __init__(self, coordinator: ConnectairCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "fan")

    @property
    def supported_features(self) -> FanEntityFeature:
        """Advertise stop only when the unit exposes an enabled stop control."""
        state = self.device_state
        features = self._attr_supported_features
        if state is not None and state.controls.supports_stop:
            features |= FanEntityFeature.TURN_OFF
        return features

    @property
    def percentage(self) -> int | None:
        """Map four reported speed levels to native HA percentages."""
        state = self.device_state
        if state is None or state.speed is None:
            return None
        if 0 <= state.speed <= 4:
            return state.speed * 25
        return None

    @property
    def is_on(self) -> bool | None:
        state = self.device_state
        return None if state is None or state.speed is None else state.speed > 0

    async def async_set_percentage(self, percentage: int) -> None:
        """Round upward to a supported manual speed; validate optional stop."""
        if not 0 <= percentage <= 100:
            raise HomeAssistantError("Percentage must be between 0 and 100")
        if percentage == 0 and FanEntityFeature.TURN_OFF not in self.supported_features:
            raise HomeAssistantError("This unit does not expose an enabled stop control")
        await self.coordinator.async_set_speed(self.device_id, math.ceil(percentage / 25))

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        """Start at low unless a speed has been explicitly requested."""
        if preset_mode is not None:
            raise HomeAssistantError("Connectair supports manual percentages, not preset modes")
        await self.async_set_percentage(percentage if percentage is not None else 25)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_set_percentage(0)
