"""Native entities expose reported values and route speed commands safely."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.components.fan import FanEntityFeature
from homeassistant.exceptions import HomeAssistantError
from test_coordinator import PollClient, make_state

from custom_components.connectair.binary_sensor import ConnectairOnlineSensor
from custom_components.connectair.coordinator import ConnectairCoordinator
from custom_components.connectair.diagnostics import async_get_config_entry_diagnostics
from custom_components.connectair.fan import ConnectairFan
from custom_components.connectair.models import TransportError, UnsupportedDeviceError
from custom_components.connectair.sensor import ConnectairSensor


@pytest.mark.parametrize("speed, expected", [(0, 0), (1, 25), (2, 50), (3, 75), (4, 100)])
async def test_fan_percentage_uses_reported_speed(hass, account_entry, speed, expected):
    client = PollClient()
    client.states["unit-a"] = make_state(speed=speed)
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    fan = ConnectairFan(coordinator, "unit-a")
    assert fan.percentage == expected
    assert fan.is_on is (speed > 0)
    assert fan.preset_modes is None
    assert FanEntityFeature.SET_SPEED in fan.supported_features


@pytest.mark.parametrize(
    "percentage, expected", [(1, 1), (25, 1), (26, 2), (50, 2), (75, 3), (100, 4)]
)
async def test_fan_service_rounds_to_supported_speed(hass, account_entry, percentage, expected):
    coordinator = ConnectairCoordinator(hass, account_entry, PollClient())
    await coordinator.async_refresh()
    fan = ConnectairFan(coordinator, "unit-a")
    await fan.async_set_percentage(percentage)
    assert coordinator.data["unit-a"].speed == expected


@pytest.mark.parametrize("action", ["turn_off", "zero_percentage"])
async def test_hidden_stop_does_not_advertise_or_send_off(hass, account_entry, action):
    coordinator = ConnectairCoordinator(hass, account_entry, PollClient())
    await coordinator.async_refresh()
    fan = ConnectairFan(coordinator, "unit-a")
    assert FanEntityFeature.SET_SPEED in fan.supported_features
    assert FanEntityFeature.TURN_ON in fan.supported_features
    assert FanEntityFeature.TURN_OFF not in fan.supported_features
    with pytest.raises(HomeAssistantError, match="stop"):
        if action == "turn_off":
            await fan.async_turn_off()
        else:
            await fan.async_set_percentage(0)
    assert coordinator.data["unit-a"].speed == 4


async def test_visible_enabled_stop_allows_off_and_uses_reported_result(hass, account_entry):
    client = PollClient()
    client.states["unit-a"] = make_state(stop=True)
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    fan = ConnectairFan(coordinator, "unit-a")
    assert FanEntityFeature.TURN_OFF in fan.supported_features
    await fan.async_turn_off()
    assert fan.percentage == 0
    assert fan.is_on is False


async def test_unknown_speed_is_unknown_and_offline_device_is_unavailable(hass, account_entry):
    coordinator = ConnectairCoordinator(hass, account_entry, PollClient())
    await coordinator.async_refresh()
    coordinator.data["unit-a"] = make_state(speed=None)
    fan = ConnectairFan(coordinator, "unit-a")
    assert fan.percentage is None
    assert fan.is_on is None
    coordinator.data["unit-a"] = None
    coordinator.devices["unit-a"].online = False
    assert not fan.available
    assert not ConnectairOnlineSensor(coordinator, "unit-a").is_on
    assert ConnectairOnlineSensor(coordinator, "unit-a").available


@pytest.mark.parametrize(
    "failure", [TransportError("unreachable"), UnsupportedDeviceError("unsupported")]
)
async def test_dashboard_failure_does_not_override_device_list_connectivity(
    hass, account_entry, failure
):
    client = PollClient()
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    fan = ConnectairFan(coordinator, "unit-b")
    connectivity = ConnectairOnlineSensor(coordinator, "unit-b")
    client.failures["unit-b"] = failure
    await coordinator.async_refresh()
    assert not fan.available
    assert connectivity.available
    assert connectivity.is_on is True
    client.states.pop("unit-b")
    await coordinator.async_refresh()
    assert connectivity.is_on is None


async def test_connectivity_is_unavailable_when_account_poll_fails(hass, account_entry):
    client = PollClient()
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    connectivity = ConnectairOnlineSensor(coordinator, "unit-a")

    async def unavailable_list():
        raise TransportError("account unreachable")

    client.async_list_devices = unavailable_list
    await coordinator.async_refresh()
    assert not connectivity.available


async def test_invalid_percentage_cannot_send_a_command(hass, account_entry):
    coordinator = ConnectairCoordinator(hass, account_entry, PollClient())
    await coordinator.async_refresh()
    fan = ConnectairFan(coordinator, "unit-a")
    with pytest.raises(HomeAssistantError):
        await fan.async_set_percentage(-1)
    assert coordinator.data["unit-a"].speed == 4


async def test_sensor_reports_raw_values_without_inventing_modes(hass, account_entry):
    coordinator = ConnectairCoordinator(hass, account_entry, PollClient())
    await coordinator.async_refresh()
    assert ConnectairSensor(coordinator, "unit-a", "mode").native_value == 0
    assert ConnectairSensor(coordinator, "unit-a", "speed").native_value == 4
    assert ConnectairSensor(coordinator, "unit-a", "filter_days").native_value == 180


async def test_diagnostics_never_export_account_or_raw_dashboard(hass, account_entry):
    coordinator = ConnectairCoordinator(hass, account_entry, PollClient())
    await coordinator.async_refresh()
    coordinator.data["unit-a"].dashboard = {"password": "secret", "user": "private@example.com"}
    account_entry.runtime_data = coordinator
    output = await async_get_config_entry_diagnostics(hass, account_entry)
    rendered = str(output)
    assert "secret" not in rendered
    assert "private@example.com" not in rendered
    assert "unit-a" not in rendered
    assert "account-a" not in rendered
    assert output["devices"][0]["speed"] == 4


async def test_diagnostics_retain_device_connectivity_when_dashboard_unavailable(
    hass, account_entry
):
    client = PollClient()
    client.failures["unit-b"] = TransportError("dashboard unavailable")
    coordinator = ConnectairCoordinator(hass, account_entry, client)
    await coordinator.async_refresh()
    account_entry.runtime_data = coordinator
    output = await async_get_config_entry_diagnostics(hass, account_entry)
    assert output["devices"][1]["online"] is True
    assert output["devices"][1]["speed"] is None


@pytest.mark.parametrize(
    "stored_data",
    [
        {},
        {"tokens": None},
        {"tokens": "malformed"},
        {"tokens": {"access_token": "test", "expires_at": 1}},
        {"tokens": {"access_token": "test", "refresh_token": "test", "expires_at": "invalid"}},
    ],
)
async def test_malformed_stored_credentials_start_reauth_instead_of_generic_setup_failure(
    hass, account_entry, enable_custom_integrations, stored_data
):
    hass.config_entries.async_update_entry(account_entry, data=stored_data)
    assert not await hass.config_entries.async_setup(account_entry.entry_id)
    await hass.async_block_till_done()
    progress = hass.config_entries.flow.async_progress_by_handler("connectair")
    assert any(
        flow["context"]["source"] == config_entries.SOURCE_REAUTH
        and flow["context"]["entry_id"] == account_entry.entry_id
        for flow in progress
    )


async def test_setup_creates_native_entities_and_unload_marks_them_unavailable(
    hass, account_entry, enable_custom_integrations
):
    hass.config_entries.async_update_entry(
        account_entry,
        data={
            "tokens": {
                "access_token": "test-access",
                "refresh_token": "test-refresh",
                "expires_at": 1,
            }
        },
    )
    client = PollClient()
    with patch("custom_components.connectair.api.ConnectairClient", return_value=client):
        assert await hass.config_entries.async_setup(account_entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get("fan.unit_a").attributes["percentage"] == 100
    assert hass.states.get("fan.unit_b").attributes["percentage"] == 25
    assert hass.states.get("sensor.unit_a_reported_mode").state == "0"
    assert hass.states.get("binary_sensor.unit_a_online").state == "on"
    assert not hass.states.async_entity_ids("button")
    assert await hass.config_entries.async_unload(account_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("fan.unit_a").state == "unavailable"
    assert hass.states.get("fan.unit_b").state == "unavailable"


async def test_unverified_device_has_no_control_then_is_added_after_valid_metadata(
    hass, account_entry, enable_custom_integrations
):
    hass.config_entries.async_update_entry(
        account_entry,
        data={"tokens": {"access_token": "test", "refresh_token": "test", "expires_at": 1}},
    )
    client = PollClient()
    client.failures["unit-b"] = UnsupportedDeviceError("no known controls")
    with patch("custom_components.connectair.api.ConnectairClient", return_value=client):
        assert await hass.config_entries.async_setup(account_entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get("fan.unit_a").attributes["percentage"] == 100
    assert hass.states.get("fan.unit_b") is None
    client.failures.clear()
    await account_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("fan.unit_b").attributes["percentage"] == 25
