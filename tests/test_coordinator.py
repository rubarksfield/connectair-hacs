"""Account polling must isolate failures and publish confirmed commands only."""

import asyncio
import traceback
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.connectair.coordinator import ConnectairCoordinator
from custom_components.connectair.models import AuthenticationError, CommandError, TransportError


def make_state(device_id="unit-a", *, speed=4, mode=0, online=True, boost=False, stop=False):
    """Complete boundary state; independent of production parsing."""
    return SimpleNamespace(
        device=SimpleNamespace(
            device_id=device_id, name=device_id, model="NARAH 160 RT", online=online
        ),
        speed=speed,
        mode=mode,
        filter_days=180,
        dashboard={},
        controls=SimpleNamespace(boost_available=boost, supports_stop=stop),
    )


class PollClient:
    """External API double with literal reported state and real failures."""

    def __init__(self):
        self.states = {"unit-a": make_state(), "unit-b": make_state("unit-b", speed=1)}
        self.failures = {}
        self.command_error = None

    async def async_list_devices(self):
        return [state.device for state in self.states.values()]

    async def async_get_state(self, device_id):
        if device_id in self.failures:
            raise self.failures[device_id]
        return self.states[device_id]

    async def async_set_speed(self, device_id, speed):
        if self.command_error:
            raise self.command_error
        self.states[device_id] = make_state(
            device_id, speed=speed, mode=0, stop=self.states[device_id].controls.supports_stop
        )
        return self.states[device_id]


async def test_one_device_transport_failure_keeps_other_device_available(hass, account_entry):
    client = PollClient()
    client.failures["unit-b"] = TransportError("temporarily unreachable")
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.data["unit-a"].speed == 4
    assert coordinator.data["unit-b"] is None


async def test_account_auth_failure_starts_reauthentication(hass, account_entry):
    client = PollClient()
    client.failures["unit-a"] = AuthenticationError("expired login")
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.parametrize(
    ("provider_error", "surface_error"),
    [
        (AuthenticationError, ConfigEntryAuthFailed),
        (TransportError, UpdateFailed),
        (CommandError, UpdateFailed),
    ],
)
async def test_account_poll_tracebacks_omit_provider_details(
    hass, account_entry, provider_error, surface_error
):
    private_marker = "synthetic-private-account-marker"
    client = PollClient()

    async def failed_device_list():
        raise provider_error(private_marker)

    client.async_list_devices = failed_device_list
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    with pytest.raises(surface_error) as caught:
        await coordinator._async_update_data()
    assert private_marker not in "".join(traceback.format_exception(caught.value))


async def test_device_auth_poll_traceback_omits_provider_details(hass, account_entry):
    private_marker = "synthetic-private-account-marker"
    client = PollClient()
    client.failures["unit-a"] = AuthenticationError(private_marker)
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    with pytest.raises(ConfigEntryAuthFailed) as caught:
        await coordinator._async_update_data()
    assert private_marker not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("provider_error", [AuthenticationError, CommandError])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_command_tracebacks_omit_provider_details_and_preserve_reported_state(
    hass, account_entry, provider_error
):
    private_marker = "synthetic-private-command-marker"
    client = PollClient()
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    client.command_error = provider_error(private_marker)
    with pytest.raises(HomeAssistantError) as caught:
        await coordinator.async_set_speed("unit-a", 1)
    assert private_marker not in "".join(traceback.format_exception(caught.value))
    assert coordinator.data["unit-a"].speed == 4


async def test_command_replaces_state_only_after_api_confirmation(hass, account_entry):
    client = PollClient()
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    await coordinator.async_set_speed("unit-a", 1)
    assert coordinator.data["unit-a"].speed == 1
    client.command_error = CommandError("device did not confirm")
    with pytest.raises(HomeAssistantError):
        await coordinator.async_set_speed("unit-a", 4)
    assert coordinator.data["unit-a"].speed == 1


async def test_poll_started_before_command_cannot_overwrite_confirmed_result(hass, account_entry):
    client = PollClient()
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    started, finish = asyncio.Event(), asyncio.Event()
    read_state = client.async_get_state

    async def delayed_read(device_id):
        snapshot = await read_state(device_id)
        if device_id == "unit-a":
            started.set()
            await finish.wait()
        return snapshot

    client.async_get_state = delayed_read
    poll = asyncio.create_task(coordinator.async_refresh())
    await started.wait()
    await coordinator.async_set_speed("unit-a", 1)
    finish.set()
    await poll
    assert coordinator.data["unit-a"].speed == 1
