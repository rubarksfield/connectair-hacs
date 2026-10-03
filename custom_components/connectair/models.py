"""Connectair metadata parsing and command construction, independent of Home Assistant."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class ConnectairError(Exception):
    """Base error for a safe Connectair operation."""


class AuthenticationError(ConnectairError):
    """Login is missing, expired, or rejected."""


class TransportError(ConnectairError):
    """The cloud service could not be reached."""


class ProtocolError(ConnectairError):
    """The cloud response cannot be safely interpreted."""


class UnsupportedDeviceError(ConnectairError):
    """The device or requested control is not supported."""


class DeviceOfflineError(ConnectairError):
    """An offline device cannot accept a control command."""


class CommandError(ConnectairError):
    """A command was rejected or its reported result was not confirmed."""


@dataclass(frozen=True, slots=True)
class Device:
    """Only the device identity fields needed by the integration."""

    device_id: str
    name: str
    model: str
    online: bool


@dataclass(frozen=True, slots=True)
class Controls:
    """Runtime-discovered controls; group IDs are never inferred from a model."""

    speed_group: dict[str, Any]
    manual_group: dict[str, Any]
    groups: tuple[dict[str, Any], ...]
    boost_available: bool

    @property
    def supports_stop(self) -> bool:
        """Expose Stop only when the app makes the option visible and enabled."""
        options = [o for o in _options(self.speed_group) if o.get("register") == "Parado"]
        return (
            self.speed_group.get("isVisible") is True
            and len(options) == 1
            and options[0].get("isVisible") is True
            and options[0].get("state") in (0, 1)
        )


@dataclass(frozen=True, slots=True)
class DeviceState:
    """Reported registers, not optimistic or possibly stale UI selections."""

    device: Device
    speed: int | None
    mode: int | None
    filter_days: int | None
    dashboard: dict[str, Any]
    controls: Controls


@dataclass(frozen=True, slots=True)
class DeviceMeasurements:
    """Optional ambient readings from one Connectair state response."""

    humidity: float | None
    temperature: float | None


SPEED_REGISTERS = {0: "Parado", 1: "Speed1de4", 2: "Speed2de4", 3: "Speed3de4", 4: "Speed4de4"}
_SPEED_CLASSES = {
    "Parado": 47,
    "Speed1de4": 126,
    "Speed2de4": 129,
    "Speed3de4": 130,
    "Speed4de4": 131,
    "HighSpeed": 9,
}
_SUPPORTED_MODELS = {"NARAH 160 RT", "P0024_R000"}


def parse_device(data: dict[str, Any]) -> Device:
    """Normalize both list items and device-detail response fields."""
    device_id = data.get("deviceId")
    if not isinstance(device_id, (str, int)) or isinstance(device_id, bool) or not str(device_id):
        raise ProtocolError("Device response has no valid device ID")
    nested_model = data.get("model")
    model = data.get("productName") or data.get("modelName")
    if not model:
        model = nested_model.get("model") if isinstance(nested_model, dict) else nested_model
    name = data.get("projectName") or data.get("project") or data.get("name") or str(device_id)
    online = data.get("isOnline", data.get("online"))
    if not isinstance(online, bool):
        raise ProtocolError("Device response has no valid online status")
    if not isinstance(model, str) or not isinstance(name, str):
        raise ProtocolError("Device response has invalid metadata")
    return Device(str(device_id), name.strip(), model.strip(), online)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = int(value)
        if isinstance(value, float) and result != value:
            return None
        return result
    except ValueError, TypeError, OverflowError:
        return None


def _options(group: dict[str, Any]) -> list[dict[str, Any]]:
    """Collapse exact cloud duplicates without hiding conflicting metadata."""
    options = group.get("sensors")
    if (
        not isinstance(options, list)
        or not options
        or not all(isinstance(o, dict) for o in options)
    ):
        raise ProtocolError("Dashboard contains invalid control options")
    unique = []
    seen: set[str] = set()
    for option in options:
        # Full JSON records preserve distinctions such as true versus 1.
        fingerprint = json.dumps(option, sort_keys=True)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(option)
    return unique


def _flatten_dashboard(dashboard: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    try:
        sections = dashboard["dashboardSections"]
        if not isinstance(sections, list):
            raise TypeError
        result = []
        for section in sections:
            if section.get("name", "").lower() == "alarm":
                continue
            for zone in section["frameZoneTypes"]:
                for container in zone["sensorGroupContainers"]:
                    for group in container["sensorGroups"]:
                        if not isinstance(group, dict) or not isinstance(group.get("id"), int):
                            raise TypeError
                        _options(group)
                        if not group.get("isCloned", False):
                            result.append({**group, "_dashboard_name": zone.get("dashboardName")})
        return tuple(result)
    except (KeyError, TypeError, AttributeError) as err:
        raise ProtocolError("Dashboard response has invalid structure") from err


def _read_register(groups: tuple[dict[str, Any], ...], register: str) -> int | None:
    readings = set()
    for group in groups:
        options = _options(group)
        if group.get("sensorGroupTypeId") != 1 or len(options) != 1:
            continue
        option = options[0]
        if option.get("register") == register:
            raw = option.get("valueRaw")
            if raw is None:
                raw = group.get("selectedValue")
            reading = _integer(raw)
            if reading is not None:
                readings.add(reading)
    if len(readings) > 1:
        raise ProtocolError("Dashboard has conflicting reported registers")
    return next(iter(readings), None)


def parse_dashboard(device: Device, dashboard: dict[str, Any]) -> DeviceState:
    """Reject ambiguous metadata before making controls available."""
    if device.model.strip().upper() not in _SUPPORTED_MODELS:
        raise UnsupportedDeviceError("Only NARAH 160 RT is supported")
    if not isinstance(dashboard, dict):
        raise ProtocolError("Dashboard response must be an object")
    groups = _flatten_dashboard(dashboard)
    speed_candidates = []
    manual_candidates = []
    for group in groups:
        options = _options(group)
        registers = {o.get("register") for o in options}
        if group.get("_dashboard_name") in ("NightMode", "HolidayMode"):
            continue
        if group.get("sensorGroupTypeId") == 3 and set(SPEED_REGISTERS.values()).issubset(
            registers
        ):
            speed_candidates.append(group)
        if group.get("sensorGroupTypeId") == 4 and "Mode_manual" in registers:
            manual_candidates.append(group)
    if len(speed_candidates) != 1 or len(manual_candidates) != 1:
        raise UnsupportedDeviceError("Dashboard has no unique four-speed manual control")
    speed_group, manual_group = speed_candidates[0], manual_candidates[0]
    for register, expected_class in _SPEED_CLASSES.items():
        options = [o for o in _options(speed_group) if o.get("register") == register]
        if register == "HighSpeed" and not options:
            continue
        if len(options) != 1 or options[0].get("elementClassId") != expected_class:
            raise UnsupportedDeviceError("Dashboard has unrecognized speed controls")
    manual_options = [o for o in _options(manual_group) if o.get("register") == "Mode_manual"]
    if len(manual_options) != 1 or manual_options[0].get("elementClassId") != 32:
        raise UnsupportedDeviceError("Dashboard has unrecognized manual control")
    boost = any(
        o.get("register") == "HighSpeed" and o.get("state") != -1 and o.get("isVisible", False)
        for o in _options(speed_group)
    )
    speed = _read_register(groups, "HR4")
    if speed is not None and speed not in range(5):
        speed = None
    return DeviceState(
        device,
        speed,
        _read_register(groups, "HR3"),
        _read_register(groups, "IR20"),
        dashboard,
        Controls(speed_group, manual_group, groups, boost),
    )


def _equal(left: Any, right: Any) -> bool:
    """Relevant subset of JS loose equality for server option values."""
    if left is None or right is None:
        return left is right
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        try:
            return float(left) == float(right)
        except TypeError, ValueError:
            return False
    return left == right


def build_command(state: DeviceState, group: dict[str, Any], register: str) -> dict[str, Any]:
    """Follow the web client's parent/child snapshot algorithm in runtime order."""
    if not state.device.online:
        raise DeviceOfflineError("Device is offline")
    if not any(candidate is group for candidate in state.controls.groups):
        raise UnsupportedDeviceError("Control is not part of the fresh dashboard")
    if (
        group is state.controls.speed_group
        and register == "Parado"
        and not state.controls.supports_stop
    ):
        raise UnsupportedDeviceError("Stop is not enabled for this device")
    options = _options(group)
    matching = [o for o in options if o.get("register") == register]
    if len(matching) != 1 or matching[0].get("state") == -1:
        raise UnsupportedDeviceError("Requested control is missing or disabled")
    chosen = matching[0]
    current = next(
        (o for o in options if _equal(o.get("value"), group.get("selectedValue"))), options[0]
    )
    from_class = current.get("elementClassId") or options[0].get("elementClassId") or -1
    group_type = group.get("sensorGroupTypeId")
    snapshots = []
    child_key = 0
    for other in state.controls.groups:
        if other.get("sensorGroupTypeId") not in (4, 8):
            continue
        other_options = _options(other)
        if other.get("selectedValue") is not None and not any(
            _equal(o.get("value"), other["selectedValue"]) for o in other_options
        ):
            raise ProtocolError("Cannot preserve an unknown coupled selection")
        elements = []
        for option in other_options:
            same_group = other["id"] == group["id"]
            from_selected = False
            is_child = False
            if group_type == 4:
                selected = same_group and _equal(option.get("value"), chosen.get("value"))
                if selected:
                    child_key = _integer(option.get("keyIdentificationChildren")) or 0
                from_selected = _equal(other.get("selectedValue"), option.get("value"))
            elif group_type == 8 and same_group:
                selected = _equal(option.get("value"), chosen.get("value"))
            else:
                selected = _equal(other.get("selectedValue"), option.get("value"))
            if child_key > 0 and option.get("keyidentification") == child_key:
                selected, from_selected, is_child = True, False, True
            elements.append(
                {
                    "sensorElementClassId": option.get("elementClassId") or -1,
                    "lastValue": int(is_child or same_group),
                    "selected": int(selected),
                    "fromSelected": int(from_selected),
                }
            )
        snapshots.append({"sensorGroupId": other["id"], "sensorsGroupElementList": elements})
    raw_value = chosen.get("valueRaw")
    if raw_value is None:
        raw_value = (
            chosen.get("value")
            if group_type == 1
            else int(group_type == 4 and bool(chosen.get("value")))
        )
    return {
        "interaction": {
            "sensorGroupId": group["id"],
            "sensorId": register,
            "sensorValueId": raw_value,
            "sensorGroupTypeId": group_type,
            "fromSensorElementClassId": from_class,
            "toSensorElementClassId": chosen.get("elementClassId") or from_class,
        },
        "sensorGroups": snapshots or None,
    }
