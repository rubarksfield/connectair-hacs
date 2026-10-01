"""Account polling must isolate failures and publish confirmed commands only."""

import asyncio
import traceback
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.connectair.coordinator import ConnectairCoordinator
from custom_components.connectair.models import (
    AuthenticationError,
    CommandError,
    ProtocolError,
    TransportError,
    UnsupportedDeviceError,
)


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
        self.humidity_values = {"unit-a": 42.5, "unit-b": 61.0}
        self.humidity_failures = {}
        self.humidity_requests = []

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

    async def async_get_humidity(self, device_id):
        self.humidity_requests.append(device_id)
        if device_id in self.humidity_failures:
            raise self.humidity_failures[device_id]
        return self.humidity_values.get(device_id)


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


@pytest.mark.parametrize("error", [TransportError("unreachable"), ProtocolError("malformed")])
async def test_humidity_failure_clears_only_that_measurement(hass, account_entry, error):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    humidity = fan.humidity_coordinator
    await humidity.async_refresh()
    assert humidity.data == {"unit-a": 42.5, "unit-b": 61.0}
    client.humidity_failures["unit-a"] = error
    await humidity.async_refresh()
    assert humidity.data == {"unit-a": None, "unit-b": 61.0}
    assert fan.last_update_success
    assert fan.data["unit-a"].speed == 4
    await fan.async_set_speed("unit-a", 1)
    assert fan.data["unit-a"].speed == 1


async def test_pending_humidity_read_does_not_delay_fan_poll_or_command(hass, account_entry):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    started, finish = asyncio.Event(), asyncio.Event()
    read_humidity = client.async_get_humidity

    async def delayed_humidity(device_id):
        if device_id == "unit-a":
            started.set()
            await finish.wait()
        return await read_humidity(device_id)

    client.async_get_humidity = delayed_humidity
    poll = asyncio.create_task(fan.humidity_coordinator.async_refresh())
    await started.wait()
    try:
        await fan.async_refresh()
        await fan.async_set_speed("unit-a", 1)
        assert not poll.done()
        assert fan.data["unit-a"].speed == 1
        assert fan.last_update_success
    finally:
        finish.set()
        await poll


async def test_command_does_not_refresh_humidity(hass, account_entry):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    await fan.humidity_coordinator.async_refresh()
    client.humidity_requests.clear()
    await fan.async_set_speed("unit-a", 1)
    assert fan.data["unit-a"].speed == 1
    assert client.humidity_requests == []


async def test_parent_offline_and_removed_devices_clear_humidity_immediately(hass, account_entry):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    humidity = fan.humidity_coordinator
    await humidity.async_refresh()
    client.states["unit-a"].device.online = False
    client.states.pop("unit-b")
    await fan.async_refresh()
    assert humidity.data.get("unit-a") is None
    assert humidity.data.get("unit-b") is None
    client.humidity_requests.clear()
    await humidity.async_refresh()
    assert client.humidity_requests == []
    assert humidity.data == {"unit-a": None}


async def test_late_humidity_response_cannot_restore_offline_measurement(hass, account_entry):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    humidity = fan.humidity_coordinator
    await humidity.async_refresh()
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed_humidity(device_id):
        if device_id == "unit-a":
            started.set()
            await finish.wait()
        return 42.5

    client.async_get_humidity = delayed_humidity
    poll = asyncio.create_task(humidity.async_refresh())
    await started.wait()
    try:
        client.states["unit-a"].device.online = False
        await fan.async_refresh()
    finally:
        finish.set()
        await poll
    assert humidity.data["unit-a"] is None


async def test_parent_account_failure_clears_humidity_without_more_measurement_reads(
    hass, account_entry
):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    humidity = fan.humidity_coordinator
    await humidity.async_refresh()

    async def failed_account():
        raise TransportError("unreachable")

    client.async_list_devices = failed_account
    await fan.async_refresh()
    assert humidity.data == {"unit-a": None, "unit-b": None}
    client.humidity_requests.clear()
    await humidity.async_refresh()
    assert client.humidity_requests == []


async def test_humidity_auth_traceback_omits_private_provider_details(hass, account_entry):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    client.humidity_failures["unit-a"] = AuthenticationError("synthetic-private-auth-marker")
    with pytest.raises(ConfigEntryAuthFailed) as caught:
        await fan.humidity_coordinator._async_update_data()
    assert "synthetic-private-auth-marker" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("transition", ["offline", "removed"])
async def test_delayed_humidity_cannot_restore_reading_after_disconnect_and_reconnect(
    hass, account_entry, transition
):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    humidity = fan.humidity_coordinator
    await humidity.async_refresh()
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed_humidity(device_id):
        if device_id == "unit-a":
            started.set()
            await finish.wait()
        return 42.5

    client.async_get_humidity = delayed_humidity
    poll = asyncio.create_task(humidity.async_refresh())
    await started.wait()
    try:
        if transition == "offline":
            client.states["unit-a"].device.online = False
        else:
            client.states.pop("unit-a")
        await fan.async_refresh()
        client.states["unit-a"] = make_state()
        await fan.async_refresh()
    finally:
        finish.set()
        await poll
    assert humidity.data["unit-a"] is None
    # Another fan's uninterrupted reading is not discarded by the transition.
    assert humidity.data["unit-b"] == 42.5


async def test_fresh_detail_offline_invalidates_humidity_even_when_list_says_online(
    hass, account_entry
):
    client = PollClient()
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    humidity = fan.humidity_coordinator
    await humidity.async_refresh()
    list_devices = await client.async_list_devices()

    async def unchanged_list():
        return list_devices

    client.async_list_devices = unchanged_list
    client.states["unit-a"] = make_state(online=False)
    await fan.async_refresh()
    assert fan.devices["unit-a"].online
    assert not fan.data["unit-a"].device.online
    assert humidity.data["unit-a"] is None
    client.humidity_requests.clear()
    await humidity.async_refresh()
    assert client.humidity_requests == ["unit-b"]


async def test_humidity_skips_never_supported_device_but_keeps_validated_transient_failure(
    hass, account_entry
):
    client = PollClient()
    client.failures["unit-b"] = UnsupportedDeviceError("unsupported controls")
    fan = ConnectairCoordinator(hass, account_entry, client)
    await fan.async_refresh()
    humidity = fan.humidity_coordinator
    await humidity.async_refresh()
    assert client.humidity_requests == ["unit-a"]
    client.failures["unit-a"] = TransportError("temporary dashboard failure")
    await fan.async_refresh()
    client.humidity_requests.clear()
    await humidity.async_refresh()
    assert client.humidity_requests == ["unit-a"]
    assert humidity.data["unit-a"] == 42.5
