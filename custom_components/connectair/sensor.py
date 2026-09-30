"""Reported register values without inferred operating modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ConnectairCoordinator, ConnectairEntity, async_add_device_entities

if TYPE_CHECKING:
    from . import ConnectairConfigEntry

SENSOR_NAMES = {
    "mode": "Reported mode",
    "speed": "Reported speed",
    "filter_days": "Filter remaining",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConnectairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda c, d: [ConnectairSensor(c, d, key) for key in SENSOR_NAMES],
        require_supported_state=True,
    )


class ConnectairSensor(ConnectairEntity, SensorEntity):
    """Expose a raw device report; unknown values remain unknown."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ConnectairCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator, device_id, key)
        self.key = key
        self._attr_name = SENSOR_NAMES[key]
        if key == "filter_days":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.DAYS
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:air-filter"
        else:
            self._attr_icon = "mdi:fan" if key == "speed" else "mdi:cog-outline"

    @property
    def native_value(self) -> int | None:
        state = self.device_state
        return getattr(state, self.key) if state is not None else None
