"""Reported register values without inferred operating modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    ConnectairCoordinator,
    ConnectairEntity,
    ConnectairHumidityCoordinator,
    async_add_device_entities,
)

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
        lambda c, d: [
            *(ConnectairSensor(c, d, key) for key in SENSOR_NAMES),
            ConnectairHumiditySensor(c.humidity_coordinator, d),
            ConnectairTemperatureSensor(c.humidity_coordinator, d),
        ],
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


class ConnectairHumiditySensor(CoordinatorEntity[ConnectairHumidityCoordinator], SensorEntity):
    """Expose a validated ambient RH reading, without inventing a sample timestamp."""

    _attr_has_entity_name = True
    _attr_name = "Humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ConnectairHumidityCoordinator, device_id: str) -> None:
        super().__init__(coordinator, context=device_id)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_humidity"
        device = coordinator.parent.devices[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device.name,
            manufacturer="Soler & Palau",
            model=device.model,
            configuration_url="https://www.connectairapp.com",
        )

    @property
    def native_value(self) -> float | None:
        measurements = self.coordinator.data.get(self.device_id)
        return measurements.humidity if measurements is not None else None

    @property
    def available(self) -> bool:
        parent = self.coordinator.parent
        device = parent.devices.get(self.device_id)
        return (
            super().available
            and parent.last_update_success
            and device is not None
            and device.online
            and self.native_value is not None
        )


class ConnectairTemperatureSensor(ConnectairHumiditySensor):
    """Expose the unit's reported ambient temperature in Celsius."""

    _attr_name = "Temperature"
    _attr_unique_id = None
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: ConnectairHumidityCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_temperature"

    @property
    def native_value(self) -> float | None:
        measurements = self.coordinator.data.get(self.device_id)
        return measurements.temperature if measurements is not None else None
