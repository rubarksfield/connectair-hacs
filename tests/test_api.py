"""Exercise the real cloud client with HTTP-boundary response fixtures."""

import asyncio
import copy

import aiohttp
import pytest
import pytest_asyncio
from aioresponses import CallbackResult, aioresponses
from test_models import dashboard_fixture, groups

from custom_components.connectair.api import ConnectairClient
from custom_components.connectair.models import (
    AuthenticationError,
    CommandError,
    DeviceOfflineError,
    ProtocolError,
    TransportError,
    UnsupportedDeviceError,
)

BASE = "https://spportalwebapp-pro.azurewebsites.net/api"
DEVICE = {
    "deviceId": "demo-unit",
    "project": "Ventilation",
    "modelName": "NARAH 160 RT",
    "model": {"model": "P0024_R000"},
    "online": True,
}


async def token_provider(force_refresh=False):
    return "test-access-token"


@pytest_asyncio.fixture
async def session():
    async with aiohttp.ClientSession() as client_session:
        yield client_session


def queue_state(responses, speed=4, mode=0, online=True):
    device = {**DEVICE, "online": online}
    dashboard = dashboard_fixture()
    groups(dashboard)[4]["sensors"][0]["valueRaw"] = speed
    groups(dashboard)[5]["sensors"][0]["valueRaw"] = mode
    responses.get(f"{BASE}/device/demo-unit", payload=device)
    responses.post(f"{BASE}/device/demo-unit/dashboard", payload=dashboard)


def client(session):
    return ConnectairClient(session, token_provider, confirmation_attempts=2, poll_interval=0)


async def test_list_follows_pagination_and_normalizes_online_items(session):
    with aioresponses() as responses:
        responses.get(
            f"{BASE}/device/list?page.size=10&page.number=1",
            payload={
                "items": [
                    {
                        "deviceId": "a",
                        "projectName": "Kitchen",
                        "productName": "NARAH 160 RT",
                        "isOnline": True,
                    }
                ],
                "total": 2,
            },
        )
        responses.get(
            f"{BASE}/device/list?page.size=10&page.number=2",
            payload={
                "items": [
                    {
                        "deviceId": "b",
                        "projectName": "Bedroom",
                        "productName": "NARAH 160 RT",
                        "isOnline": False,
                    }
                ],
                "total": 2,
            },
        )
        devices = await client(session).async_list_devices()
    assert [(d.device_id, d.name, d.online) for d in devices] == [
        ("a", "Kitchen", True),
        ("b", "Bedroom", False),
    ]


async def test_user_is_validated_at_real_endpoint(session):
    with aioresponses() as responses:
        responses.get(f"{BASE}/user/me", payload={"id": 42, "email": "owner@example.com"})
        assert await client(session).async_get_user() == {
            "id": 42,
            "email": "owner@example.com",
        }


async def test_dashboard_read_uses_units_configuration(session):
    def dashboard_response(url, **kwargs):
        assert kwargs["json"] == {
            "userConfiguration": {"volumetricFlowType": "1", "temperatureType": "8"},
        }
        return CallbackResult(payload=dashboard_fixture())

    with aioresponses() as responses:
        responses.get(f"{BASE}/device/demo-unit", payload=DEVICE)
        responses.post(f"{BASE}/device/demo-unit/dashboard", callback=dashboard_response)
        state = await client(session).async_get_state("demo-unit")
    assert (state.speed, state.mode, state.filter_days, state.device.online) == (4, 0, 119, True)


async def test_read_401_refreshes_once_and_sends_new_bearer(session):
    async def provider(force_refresh=False):
        return "fresh-token" if force_refresh else "expired-token"

    def authenticated_user(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer fresh-token"
        return CallbackResult(payload={"id": 42})

    with aioresponses() as responses:
        responses.get(f"{BASE}/user/me", status=401)
        responses.get(f"{BASE}/user/me", callback=authenticated_user)
        assert await ConnectairClient(session, provider).async_get_user() == {"id": 42}


async def test_repeated_read_401_requires_reauthentication(session):
    with aioresponses() as responses:
        responses.get(f"{BASE}/user/me", status=401, repeat=True)
        with pytest.raises(AuthenticationError):
            await client(session).async_get_user()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_read_redirect_is_rejected_even_when_its_body_looks_valid(session, status):
    with aioresponses() as responses:
        responses.get(f"{BASE}/user/me", status=status, payload={"id": 42})
        with pytest.raises(ProtocolError):
            await client(session).async_get_user()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_control_redirect_is_not_a_successful_acknowledgement(session, status):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", status=status, payload=2000)
        queue_state(responses, speed=1)
        with pytest.raises(CommandError):
            await client(session).async_set_speed("demo-unit", 1)


async def test_api_requests_disable_redirect_following(session):
    def account_response(url, **kwargs):
        assert kwargs.get("allow_redirects") is False
        return CallbackResult(payload={"id": 42})

    with aioresponses() as responses:
        responses.get(f"{BASE}/user/me", callback=account_response)
        assert await client(session).async_get_user() == {"id": 42}


async def test_speed_command_waits_for_raw_reported_change(session):
    def command_response(url, **kwargs):
        assert kwargs["json"]["interaction"] == {
            "sensorGroupId": 20,
            "sensorId": "Speed1de4",
            "sensorValueId": 0,
            "sensorGroupTypeId": 3,
            "fromSensorElementClassId": 47,
            "toSensorElementClassId": 126,
        }
        return CallbackResult(payload=2000)

    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", callback=command_response)
        queue_state(responses, speed=4)
        queue_state(responses, speed=1)
        state = await client(session).async_set_speed("demo-unit", 1)
    assert state.speed == 1


async def test_failed_acknowledgement_is_not_reported_as_success(session):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=0)
        with pytest.raises(CommandError):
            await client(session).async_set_speed("demo-unit", 1)


async def test_stale_raw_speed_exhausts_confirmation_without_repeating_write(session):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        queue_state(responses)
        queue_state(responses)
        with pytest.raises(CommandError):
            await client(session).async_set_speed("demo-unit", 1)


async def test_automatic_mode_is_confirmed_manual_before_speed_write(session):
    interactions = []

    def command_response(url, **kwargs):
        interactions.append(kwargs["json"]["interaction"])
        return CallbackResult(payload=2000)

    with aioresponses() as responses:
        queue_state(responses, mode=5)
        responses.post(f"{BASE}/activator/demo-unit", callback=command_response)
        queue_state(responses, mode=0)
        responses.post(f"{BASE}/activator/demo-unit", callback=command_response)
        queue_state(responses, speed=1)
        state = await client(session).async_set_speed("demo-unit", 1)
    assert state.speed == 1
    assert [interaction["sensorId"] for interaction in interactions] == ["Mode_manual", "Speed1de4"]


async def test_bypass_manual_mode_is_preserved_during_speed_change(session):
    with aioresponses() as responses:
        queue_state(responses, mode=2)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        queue_state(responses, speed=1, mode=2)
        state = await client(session).async_set_speed("demo-unit", 1)
    assert (state.speed, state.mode) == (1, 2)


async def test_offline_device_cannot_send_a_command(session):
    with aioresponses() as responses:
        queue_state(responses, online=False)
        with pytest.raises(DeviceOfflineError):
            await client(session).async_set_speed("demo-unit", 1)


async def test_hidden_stop_is_rejected_before_changing_automatic_mode(session):
    with aioresponses() as responses:
        queue_state(responses, mode=5)
        with pytest.raises(UnsupportedDeviceError):
            await client(session).async_set_speed("demo-unit", 0)


async def test_exposed_stop_command_requires_reported_zero_speed(session):
    dashboard = dashboard_fixture()
    groups(dashboard)[3]["sensors"][0]["isVisible"] = True
    with aioresponses() as responses:
        responses.get(f"{BASE}/device/demo-unit", payload=DEVICE)
        responses.post(f"{BASE}/device/demo-unit/dashboard", payload=dashboard)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        queue_state(responses, speed=0)
        assert (await client(session).async_set_speed("demo-unit", 0)).speed == 0


async def test_command_401_is_not_blindly_replayed(session):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", status=401)
        with pytest.raises(AuthenticationError):
            await client(session).async_set_speed("demo-unit", 1)


async def test_command_timeout_is_not_blindly_replayed(session):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", exception=TimeoutError())
        with pytest.raises(TransportError):
            await client(session).async_set_speed("demo-unit", 1)


@pytest.mark.parametrize("payload", [None, [], {"items": []}, {"items": "wrong", "total": 1}])
async def test_malformed_device_list_is_not_an_empty_account(session, payload):
    with aioresponses() as responses:
        responses.get(f"{BASE}/device/list?page.size=10&page.number=1", payload=payload)
        with pytest.raises(ProtocolError):
            await client(session).async_list_devices()


@pytest.mark.parametrize("speed", [-1, 5, True, 1.5])
async def test_invalid_speed_is_rejected_before_any_network_request(session, speed):
    with aioresponses(), pytest.raises(ValueError):
        await client(session).async_set_speed("demo-unit", speed)


async def test_device_commands_are_serialized_with_fresh_snapshots(session):
    entered = asyncio.Event()
    release = asyncio.Event()
    reads = []

    def detail_response(url, **kwargs):
        reads.append("read")
        return CallbackResult(payload=copy.deepcopy(DEVICE))

    async def first_command(url, **kwargs):
        entered.set()
        await release.wait()
        return CallbackResult(payload=2000)

    with aioresponses() as responses:
        responses.get(f"{BASE}/device/demo-unit", callback=detail_response)
        responses.post(f"{BASE}/device/demo-unit/dashboard", payload=dashboard_fixture())
        responses.post(f"{BASE}/activator/demo-unit", callback=first_command)
        queue_state(responses, speed=1)
        responses.get(f"{BASE}/device/demo-unit", callback=detail_response)
        responses.post(f"{BASE}/device/demo-unit/dashboard", payload=dashboard_fixture())
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        queue_state(responses, speed=2)
        api = client(session)
        first = asyncio.create_task(api.async_set_speed("demo-unit", 1))
        await entered.wait()
        second = asyncio.create_task(api.async_set_speed("demo-unit", 2))
        await asyncio.sleep(0)
        assert reads == ["read"]
        release.set()
        results = await asyncio.gather(first, second)
    assert [state.speed for state in results] == [1, 2]
