"""Cloud polling with isolated device failures and confirmed state updates."""

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, UPDATE_INTERVAL
from .models import AuthenticationError, ConnectairError, Device, DeviceState, TransportError

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

    async def _async_update_data(self) -> dict[str, DeviceState | None]:
        versions = self._command_versions.copy()
        try:
            devices = await self.client.async_list_devices()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed("Connectair login expired") from err
        except TransportError as err:
            raise UpdateFailed("Cannot reach Connectair cloud") from err
        except ConnectairError as err:
            raise UpdateFailed("Cannot read Connectair device list") from err
        self.devices = {device.device_id: device for device in devices}

        async def fetch(device: Device) -> DeviceState | None:
            if not device.online:
                return None
            try:
                return await self.client.async_get_state(device.device_id)
            except AuthenticationError as err:
                raise ConfigEntryAuthFailed("Connectair login expired") from err
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
        except AuthenticationError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Connectair login expired; sign in again") from err
        except ConnectairError as err:
            # Avoid forwarding provider payloads, which can contain account details.
            raise HomeAssistantError("Connectair command was not confirmed") from err
        self._command_versions[device_id] = self._command_versions.get(device_id, 0) + 1
        self.async_set_updated_data({**self.data, device_id: state})


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
    factory: Callable[[ConnectairCoordinator, str], list[ConnectairEntity]],
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
