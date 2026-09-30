"""Online state remains visible when a device itself is unavailable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ConnectairCoordinator, ConnectairEntity, async_add_device_entities

if TYPE_CHECKING:
    from . import ConnectairConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConnectairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_device_entities(
        entry, async_add_entities, lambda c, d: [ConnectairOnlineSensor(c, d)]
    )


class ConnectairOnlineSensor(ConnectairEntity, BinarySensorEntity):
    """Account polling health and per-device cloud connectivity."""

    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ConnectairCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "online")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool | None:
        state = self.device_state
        if state is not None:
            return state.device.online
        device = self.coordinator.devices.get(self.device_id)
        return device.online if device is not None else None
