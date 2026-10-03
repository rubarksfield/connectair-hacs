"""Authenticated asynchronous Connectair cloud client."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import aiohttp

from .models import (
    SPEED_REGISTERS,
    AuthenticationError,
    CommandError,
    Device,
    DeviceMeasurements,
    DeviceOfflineError,
    DeviceState,
    ProtocolError,
    TransportError,
    UnsupportedDeviceError,
    build_command,
    parse_dashboard,
    parse_device,
)

API_BASE = "https://spportalwebapp-pro.azurewebsites.net/api"
TokenProvider = Callable[..., Awaitable[str]]


class ConnectairClient:
    """A caller-owned aiohttp session and renewable, caller-owned credentials."""

    supports_boost = False  # Boost has no verified reported-state confirmation yet.

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token_provider: TokenProvider,
        *,
        confirmation_attempts: int = 61,
        poll_interval: float = 3,
        confirmation_timeout: float = 180,
    ) -> None:
        if (
            confirmation_attempts < 1
            or poll_interval < 0
            or not math.isfinite(confirmation_timeout)
            or confirmation_timeout <= 0
        ):
            raise ValueError("Invalid command confirmation settings")
        self._session = session
        self._token_provider = token_provider
        self._confirmation_attempts = confirmation_attempts
        self._poll_interval = poll_interval
        self._confirmation_timeout = confirmation_timeout
        self._command_locks: dict[str, asyncio.Lock] = {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        write: bool = False,
    ) -> Any:
        """Refresh rejected reads once; never blindly repeat a control write."""
        for attempt in range(1 if write else 2):
            token = await self._token_provider(force_refresh=attempt > 0)
            if not isinstance(token, str) or not token:
                raise AuthenticationError("Connectair login is missing")
            try:
                async with self._session.request(
                    method,
                    f"{API_BASE}{path}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Origin": "https://www.connectairapp.com",
                    },
                    json=payload,
                    params=params,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if 300 <= response.status < 400:
                        if write:
                            raise CommandError("Connectair redirected the command")
                        raise ProtocolError("Connectair redirected the read request")
                    if response.status == 401:
                        if not write and attempt == 0:
                            continue
                        raise AuthenticationError("Connectair login was rejected")
                    if response.status == 403:
                        raise AuthenticationError("Connectair account access was rejected")
                    if response.status >= 500:
                        raise TransportError("Connectair cloud service is unavailable")
                    if response.status >= 400:
                        if write:
                            raise CommandError("Connectair rejected the command")
                        raise ProtocolError("Connectair rejected the read request")
                    try:
                        return await response.json()
                    except ValueError, aiohttp.ContentTypeError:
                        # Provider exceptions can contain device URLs and private details.
                        raise ProtocolError("Connectair returned invalid JSON") from None
            except TimeoutError, aiohttp.ClientError:
                raise TransportError("Connectair cloud request failed") from None
        raise AuthenticationError("Connectair login was rejected")

    async def async_get_user(self) -> dict[str, Any]:
        """Read the authenticated account rather than trusting unverified token claims."""
        user = await self._request("GET", "/user/me")
        if not isinstance(user, dict) or not user:
            raise ProtocolError("Connectair returned an invalid account response")
        return user

    async def async_list_devices(self) -> list[Device]:
        """Read all pages; never mistake a malformed response for an empty account."""
        devices = []
        seen_ids: set[str] = set()
        page = 1
        while True:
            result = await self._request(
                "GET", "/device/list", params={"page.size": 10, "page.number": page}
            )
            if not isinstance(result, dict):
                raise ProtocolError("Connectair returned an invalid device list")
            items, total = result.get("items"), result.get("total")
            if (
                not isinstance(items, list)
                or not isinstance(total, int)
                or isinstance(total, bool)
                or total < 0
            ):
                raise ProtocolError("Connectair returned an invalid device list")
            for item in items:
                if not isinstance(item, dict):
                    raise ProtocolError("Connectair returned an invalid device item")
                device = parse_device(item)
                if device.device_id in seen_ids:
                    raise ProtocolError("Connectair device pagination repeated a device")
                devices.append(device)
                seen_ids.add(device.device_id)
            if len(devices) == total:
                return devices
            if len(devices) > total or not items or page >= 1000:
                raise ProtocolError("Connectair device pagination is incomplete")
            page += 1

    async def async_get_state(self, device_id: str) -> DeviceState:
        """Read fresh identity/online status and the complete runtime dashboard."""
        path_id = quote(str(device_id), safe="")
        detail = await self._request("GET", f"/device/{path_id}")
        if not isinstance(detail, dict):
            raise ProtocolError("Connectair returned invalid device details")
        device = parse_device(detail)
        if device.device_id != str(device_id):
            raise ProtocolError("Connectair returned a different device")
        dashboard = await self._request(
            "POST",
            f"/device/{path_id}/dashboard",
            payload={"userConfiguration": {"volumetricFlowType": "1", "temperatureType": "8"}},
        )
        return parse_dashboard(device, dashboard)

    async def async_get_measurements(self, device_id: str) -> DeviceMeasurements | None:
        """Read validated ambient readings from one state response."""
        requested_id = str(device_id)
        path_id = quote(requested_id, safe="")
        result = await self._request("GET", f"/device/{path_id}/state")
        if not isinstance(result, dict):
            raise ProtocolError("Connectair returned invalid measurement details")
        status = result.get("status")
        if (
            not isinstance(status, dict)
            or status.get("deviceId") != requested_id
            or not isinstance(status.get("isOnline"), bool)
        ):
            raise ProtocolError("Connectair returned invalid measurement identity")
        if not status["isOnline"]:
            return None
        if "reading" not in result:
            raise ProtocolError("Connectair returned invalid measurement details")
        reading = result["reading"]
        if reading is None:
            return None
        if not isinstance(reading, dict):
            raise ProtocolError("Connectair returned invalid measurement details")
        humidity = reading.get("ambientHumidity")
        if (
            isinstance(humidity, bool)
            or not isinstance(humidity, (int, float))
            or not math.isfinite(humidity)
            or not 0 <= humidity <= 100
        ):
            humidity = None
        else:
            humidity = float(humidity)

        temperature = reading.get("ambientTemperature")
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
        ):
            temperature = None
        else:
            temperature = float(temperature)

        if humidity is None and temperature is None:
            return None
        return DeviceMeasurements(humidity=humidity, temperature=temperature)

    async def async_get_humidity(self, device_id: str) -> float | None:
        """Backward-compatible humidity-only view of the measurements."""
        measurements = await self.async_get_measurements(device_id)
        return measurements.humidity if measurements is not None else None

    async def _send(self, state: DeviceState, group: dict[str, Any], register: str) -> None:
        payload = build_command(state, group, register)
        path_id = quote(state.device.device_id, safe="")
        acknowledgement = await self._request(
            "POST", f"/activator/{path_id}", payload=payload, write=True
        )
        if acknowledgement != 2000:
            raise CommandError("Connectair did not acknowledge the command")

    async def _confirm(
        self, device_id: str, predicate: Callable[[DeviceState], bool]
    ) -> DeviceState:
        """Bound reads by attempts and elapsed time; never repeat a command."""
        last_read_offline = False
        try:
            async with asyncio.timeout(self._confirmation_timeout):
                for attempt in range(self._confirmation_attempts):
                    if attempt:
                        await asyncio.sleep(self._poll_interval)
                    try:
                        state = await self.async_get_state(device_id)
                    except ProtocolError, UnsupportedDeviceError, TransportError:
                        continue
                    last_read_offline = not state.device.online
                    # The cloud can briefly report offline while an accepted command arrives.
                    if last_read_offline:
                        continue
                    if predicate(state):
                        return state
        except TimeoutError:
            pass
        if last_read_offline:
            raise DeviceOfflineError("Device remained offline during command confirmation")
        raise CommandError("Device did not report the requested state")

    async def async_set_speed(self, device_id: str, speed: int) -> DeviceState:
        """Select a manual speed, serialized against other writes for this device."""
        if not isinstance(speed, int) or isinstance(speed, bool) or speed not in SPEED_REGISTERS:
            raise ValueError("Speed must be an integer from 0 through 4")
        lock = self._command_locks.setdefault(str(device_id), asyncio.Lock())
        async with lock:
            state = await self.async_get_state(device_id)
            if not state.device.online:
                raise DeviceOfflineError("Device is offline")
            if speed == 0 and not state.controls.supports_stop:
                raise UnsupportedDeviceError("Stop is not enabled for this device")
            if state.mode not in (0, 2):
                if state.mode not in (1, 3, 4, 5):
                    raise UnsupportedDeviceError("Current operating mode cannot be safely changed")
                await self._send(state, state.controls.manual_group, "Mode_manual")
                state = await self._confirm(device_id, lambda reading: reading.mode in (0, 2))
            manual_mode = state.mode
            await self._send(state, state.controls.speed_group, SPEED_REGISTERS[speed])
            return await self._confirm(
                device_id, lambda reading: reading.speed == speed and reading.mode == manual_mode
            )
