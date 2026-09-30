"""Safe diagnostics omit all account, token and raw cloud payload data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from . import ConnectairConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConnectairConfigEntry
) -> dict:
    """Return operational state only, without household identifiers."""
    coordinator = entry.runtime_data
    return {
        "last_update_success": coordinator.last_update_success,
        "devices": [
            {
                "model": device.model,
                "online": state is not None and state.device.online,
                "speed": state.speed if state is not None else None,
                "mode": state.mode if state is not None else None,
                "filter_days": state.filter_days if state is not None else None,
                "boost_control_discovered": (
                    state.controls.boost_available if state is not None else False
                ),
            }
            for device_id, device in coordinator.devices.items()
            for state in [coordinator.data.get(device_id)]
        ],
    }
