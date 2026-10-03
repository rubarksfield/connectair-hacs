"""Cloud polling with isolated device failures and confirmed state updates."""

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, UPDATE_INTERVAL
from .models import (
    AuthenticationError,
    ConnectairError,
    Device,
    DeviceMeasurements,
    DeviceState,
    TransportError,
)

if TYPE_CHECKING:
    from . import ConnectairConfigEntry
    from .api import ConnectairClient

_LOGGER = logging.getLogger(__name__)


class ConnectairCoordinator(DataUpdateCoordinator[dict[str, DeviceState | None]]):
    """Poll one account without a failed unit hiding its healthy neighbours."""

    def __init__(self, hass: HomeAssistant, entry: ConnectairConfigEntry, client: ConnectairClient):
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=UPDATE_INTERVAL
        )
        self.client = client
        self.devices: dict[str, Device] = {}
        self.data = {}
        self._command_versions: dict[str, int] = {}
        self.humidity_coordinator = ConnectairHumidityCoordinator(hass, entry, self)

    async def _async_update_data(self) -> dict[str, DeviceState | None]:
        versions = self._command_versions.copy()
        try:
            devices = await self.client.async_list_devices()
        except AuthenticationError:
            raise ConfigEntryAuthFailed("Connectair login expired") from None
        except TransportError:
            raise UpdateFailed("Cannot reach Connectair cloud") from None
        except ConnectairError:
            raise UpdateFailed("Cannot read Connectair device list") from None
        self.devices = {device.device_id: device for device in devices}

        async def fetch(device: Device) -> DeviceState | None:
            if not device.online:
                return None
            try:
                return await self.client.async_get_state(device.device_id)
            except AuthenticationError:
                raise ConfigEntryAuthFailed("Connectair login expired") from None
            except ConnectairError:
                return None

        states = await asyncio.gather(*(fetch(device) for device in devices))
        result = dict(zip(self.devices, states, strict=True))
        for device_id in result:
            if self._command_versions.get(device_id, 0) != versions.get(device_id, 0):
                result[device_id] = self.data.get(device_id)
        return result

    async def async_set_speed(self, device_id: str, speed: int) -> None:
        """Publish only the state independently confirmed by the API client."""
        await self._async_command(device_id, self.client.async_set_speed(device_id, speed))

    async def _async_command(self, device_id: str, command) -> None:
        try:
            state = await command
        except AuthenticationError:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Connectair login expired; sign in again") from None
        except ConnectairError:
            # Avoid forwarding provider payloads, which can contain account details.
            raise HomeAssistantError("Connectair command was not confirmed") from None
        self._command_versions[device_id] = self._command_versions.get(device_id, 0) + 1
        self.async_set_updated_data({**self.data, device_id: state})


class ConnectairHumidityCoordinator(DataUpdateCoordinator[dict[str, DeviceMeasurements | None]]):
    """Read optional ambient measurements independently of fan polling."""

    def __init__(
        self, hass: HomeAssistant, entry: ConnectairConfigEntry, parent: ConnectairCoordinator
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} humidity",
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.parent = parent
        self.data = {}
        self._parent_online: dict[str, bool] = {}
        self._supported_devices: set[str] = set()
        self._availability_versions: dict[str, int] = {}
        self._next_availability_version = 0
        entry.async_on_unload(parent.async_add_listener(self._handle_parent_update))

    @callback
    def _handle_parent_update(self) -> None:
        """Invalidate stale readings immediately when the known device goes away."""
        self._supported_devices.intersection_update(self.parent.devices)
        self._supported_devices.update(
            device_id for device_id, state in self.parent.data.items() if state is not None
        )
        online = {
            device_id: (
                self.parent.last_update_success
                and device.online
                and device_id in self._supported_devices
                and ((state := self.parent.data.get(device_id)) is None or state.device.online)
            )
            for device_id, device in self.parent.devices.items()
        }
        if online == self._parent_online:
            return
        versions = {}
        for device_id, is_online in online.items():
            if self._parent_online.get(device_id) != is_online:
                self._next_availability_version += 1
                versions[device_id] = self._next_availability_version
            else:
                versions[device_id] = self._availability_versions[device_id]
        self._availability_versions = versions
        self._parent_online = online
        self.data = {
            device_id: self.data.get(device_id) if is_online else None
            for device_id, is_online in online.items()
        }
        self.async_update_listeners()

    async def _async_update_data(self) -> dict[str, DeviceMeasurements | None]:
        devices = tuple(self.parent.devices.values())
        versions = self._availability_versions.copy()

        async def fetch(device: Device) -> DeviceMeasurements | None:
            if not self._parent_online.get(device.device_id, False):
                return None
            try:
                return await self.parent.client.async_get_measurements(device.device_id)
            except AuthenticationError:
                raise ConfigEntryAuthFailed("Connectair login expired") from None
            except ConnectairError:
                return None

        try:
            readings = await asyncio.gather(*(fetch(device) for device in devices))
        except ConfigEntryAuthFailed:
            self.data = dict.fromkeys(self.parent.devices)
            raise
        result = dict(zip((device.device_id for device in devices), readings, strict=True))
        # A read begun before an offline/removed transition remains stale even
        # if that device reconnects before the response arrives.
        return {
            device_id: result.get(device_id)
            if (
                self._parent_online.get(device_id, False)
                and self._availability_versions.get(device_id) == versions.get(device_id)
            )
            else None
            for device_id in self.parent.devices
        }


class ConnectairEntity(CoordinatorEntity[ConnectairCoordinator]):
    """Stable per-device identity and availability shared by native entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ConnectairCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator, context=device_id)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        device = coordinator.devices[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device.name,
            manufacturer="Soler & Palau",
            model=device.model,
            configuration_url="https://www.connectairapp.com",
        )

    @property
    def device_state(self) -> DeviceState | None:
        """Return the latest reported device state."""
        return self.coordinator.data.get(self.device_id)

    @property
    def available(self) -> bool:
        state = self.device_state
        return super().available and state is not None and state.device.online


@callback
def async_add_device_entities(
    entry: ConnectairConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[ConnectairCoordinator, str], list[Entity]],
    *,
    require_supported_state: bool = False,
) -> None:
    """Add devices discovered now or on a subsequent successful poll."""
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_new_devices() -> None:
        entities = []
        for device_id in coordinator.devices.keys() - added:
            if require_supported_state and coordinator.data.get(device_id) is None:
                continue
            new_entities = factory(coordinator, device_id)
            if new_entities:
                entities.extend(new_entities)
                added.add(device_id)
        async_add_entities(entities)

    add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_new_devices))
