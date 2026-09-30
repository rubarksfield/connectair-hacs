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


async def test_device_list_includes_the_origin_required_by_connectair_server(session):
    def list_response(url, **kwargs):
        assert kwargs["headers"].get("Origin") == "https://www.connectairapp.com"
        assert kwargs["headers"]["Authorization"] == "Bearer test-access-token"
        return CallbackResult(payload={"items": [], "total": 0})

    with aioresponses() as responses:
        responses.get(f"{BASE}/device/list?page.size=10&page.number=1", callback=list_response)
        assert await client(session).async_list_devices() == []


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
        assert kwargs["headers"].get("Origin") == "https://www.connectairapp.com"
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


@pytest.mark.parametrize("temporary_error", ["controls", "structure", "transport"])
async def test_acknowledged_command_survives_one_temporary_confirmation_read_error(
    session, temporary_error
):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        if temporary_error == "transport":
            responses.get(f"{BASE}/device/demo-unit", status=503)
        else:
            dashboard = dashboard_fixture()
            if temporary_error == "controls":
                groups(dashboard)[3]["sensors"][2]["elementClassId"] = None
            else:
                dashboard["dashboardSections"] = None
            responses.get(f"{BASE}/device/demo-unit", payload=DEVICE)
            responses.post(f"{BASE}/device/demo-unit/dashboard", payload=dashboard)
        queue_state(responses, speed=1)
        state = await client(session).async_set_speed("demo-unit", 1)
        command_requests = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "POST" and str(url) == f"{BASE}/activator/demo-unit"
        ]
    assert state.speed == 1
    assert [len(calls) for calls in command_requests] == [1]


async def test_repeated_malformed_confirmation_reads_exhaust_without_resending_command(session):
    malformed = dashboard_fixture()
    groups(malformed)[3]["sensors"][2]["elementClassId"] = None
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        for _ in range(2):
            responses.get(f"{BASE}/device/demo-unit", payload=DEVICE)
            responses.post(f"{BASE}/device/demo-unit/dashboard", payload=malformed)
        with pytest.raises(CommandError):
            await client(session).async_set_speed("demo-unit", 1)
        command_requests = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "POST" and str(url) == f"{BASE}/activator/demo-unit"
        ]
        read_requests = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "GET" and str(url) == f"{BASE}/device/demo-unit"
        ]
    assert [len(calls) for calls in command_requests] == [1]
    assert [len(calls) for calls in read_requests] == [3]


async def test_unsupported_initial_controls_reject_without_any_command(session):
    unsupported = dashboard_fixture()
    groups(unsupported)[3]["sensors"][2]["elementClassId"] = None
    with aioresponses() as responses:
        responses.get(f"{BASE}/device/demo-unit", payload=DEVICE)
        responses.post(f"{BASE}/device/demo-unit/dashboard", payload=unsupported)
        with pytest.raises(UnsupportedDeviceError):
            await client(session).async_set_speed("demo-unit", 1)
        assert not any("/activator/" in str(url) for _, url in responses.requests)


async def test_conflicting_duplicate_initial_control_rejects_without_any_command(session):
    dashboard = dashboard_fixture()
    duplicate = copy.deepcopy(groups(dashboard)[3]["sensors"][1])
    duplicate["state"] = -1
    groups(dashboard)[3]["sensors"].append(duplicate)
    with aioresponses() as responses:
        responses.get(f"{BASE}/device/demo-unit", payload=DEVICE)
        responses.post(f"{BASE}/device/demo-unit/dashboard", payload=dashboard)
        with pytest.raises(UnsupportedDeviceError):
            await client(session).async_set_speed("demo-unit", 1)
        assert not any("/activator/" in str(url) for _, url in responses.requests)


async def test_confirmation_authentication_failure_is_not_a_transient_read_error(session):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        responses.get(f"{BASE}/device/demo-unit", status=403)
        with pytest.raises(AuthenticationError):
            await client(session).async_set_speed("demo-unit", 1)


async def test_temporary_cloud_offline_status_after_acknowledgement_can_recover(session):
    # Live evidence showed an accepted command arriving after a brief offline report.
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        queue_state(responses, speed=1, online=False)
        queue_state(responses, speed=1)
        state = await client(session).async_set_speed("demo-unit", 1)
        command_calls = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "POST" and str(url) == f"{BASE}/activator/demo-unit"
        ]
    assert (state.speed, state.device.online) == (1, True)
    assert [len(calls) for calls in command_calls] == [1]


async def test_all_offline_confirmation_reads_exhaust_without_repeating_command(session):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        queue_state(responses, speed=1, online=False)
        queue_state(responses, speed=1, online=False)
        with pytest.raises(DeviceOfflineError):
            await client(session).async_set_speed("demo-unit", 1)
        detail_calls = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "GET" and str(url) == f"{BASE}/device/demo-unit"
        ]
        command_calls = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "POST" and str(url) == f"{BASE}/activator/demo-unit"
        ]
    assert [len(calls) for calls in detail_calls] == [3]
    assert [len(calls) for calls in command_calls] == [1]


async def test_default_attempt_limit_accepts_reported_change_after_eight_stale_reads(session):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        for _ in range(9):
            queue_state(responses)
        queue_state(responses, speed=1)
        api = ConnectairClient(session, token_provider, poll_interval=0)
        assert (await api.async_set_speed("demo-unit", 1)).speed == 1


@pytest.mark.parametrize("stale_reads", [20, 31])
async def test_production_defaults_confirm_a_delayed_change(session, monkeypatch, stale_reads):
    intervals = []
    loop = asyncio.get_running_loop()
    virtual_time = [loop.time()]
    real_sleep = asyncio.sleep

    async def poll_without_waiting(interval):
        intervals.append(interval)
        virtual_time[0] += interval
        await real_sleep(0)

    monkeypatch.setattr(loop, "time", lambda: virtual_time[0])
    monkeypatch.setattr("custom_components.connectair.api.asyncio.sleep", poll_without_waiting)
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        for _ in range(stale_reads):
            queue_state(responses)
        queue_state(responses, speed=1)
        api = ConnectairClient(session, token_provider)
        assert (await api.async_set_speed("demo-unit", 1)).speed == 1
        detail_calls = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "GET" and str(url) == f"{BASE}/device/demo-unit"
        ]
        command_calls = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "POST" and str(url) == f"{BASE}/activator/demo-unit"
        ]
    assert intervals == [3] * stale_reads
    assert [len(calls) for calls in detail_calls] == [stale_reads + 2]
    assert [len(calls) for calls in command_calls] == [1]


async def test_authentication_failure_after_temporary_offline_status_still_fails_immediately(
    session,
):
    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        queue_state(responses, online=False)
        responses.get(f"{BASE}/device/demo-unit", status=403)
        with pytest.raises(AuthenticationError):
            await client(session).async_set_speed("demo-unit", 1)


@pytest.mark.parametrize("prior_offline", [False, True])
async def test_confirmation_deadline_bounds_a_blocked_http_read_without_resending_command(
    session, prior_offline
):
    entered = asyncio.Event()
    blocked = asyncio.Event()

    async def blocked_detail(url, **kwargs):
        entered.set()
        await blocked.wait()
        return CallbackResult(payload=DEVICE)

    with aioresponses() as responses:
        queue_state(responses)
        responses.post(f"{BASE}/activator/demo-unit", payload=2000)
        if prior_offline:
            queue_state(responses, speed=1, online=False)
        responses.get(f"{BASE}/device/demo-unit", callback=blocked_detail)
        api = ConnectairClient(
            session,
            token_provider,
            confirmation_attempts=20,
            poll_interval=0,
            confirmation_timeout=0.02,
        )
        expected_error = DeviceOfflineError if prior_offline else CommandError
        started = asyncio.get_running_loop().time()
        with pytest.raises(expected_error):
            await api.async_set_speed("demo-unit", 1)
        elapsed = asyncio.get_running_loop().time() - started
        command_calls = [
            calls
            for (method, url), calls in responses.requests.items()
            if method == "POST" and str(url) == f"{BASE}/activator/demo-unit"
        ]
    assert entered.is_set()
    assert elapsed < 0.5
    assert [len(calls) for calls in command_calls] == [1]


@pytest.mark.parametrize("deadline", [0, -1, float("inf"), float("nan")])
def test_confirmation_deadline_must_be_finite_and_positive(deadline):
    with pytest.raises(ValueError):
        ConnectairClient(None, token_provider, confirmation_timeout=deadline)


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
        assert not any("/activator/" in str(url) for _, url in responses.requests)


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
