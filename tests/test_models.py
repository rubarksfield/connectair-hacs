"""Literal, sanitized protocol fixtures independent of the command builder."""

import copy
import json
from pathlib import Path

import pytest

from custom_components.connectair.models import (
    Device,
    ProtocolError,
    UnsupportedDeviceError,
    build_command,
    parse_dashboard,
    parse_device,
)


def dashboard_fixture():
    return json.loads((Path(__file__).parent / "fixtures/narah_dashboard.json").read_text())


def groups(dashboard):
    return dashboard["dashboardSections"][0]["frameZoneTypes"][0]["sensorGroupContainers"][0][
        "sensorGroups"
    ]


DEVICE = Device("demo-unit", "Ventilation", "NARAH 160 RT", True)


def test_device_list_mapping_and_model_whitespace():
    assert (
        parse_device(
            {
                "deviceId": "demo-unit",
                "projectName": "Ventilation",
                "isOnline": True,
                "productName": "NARAH 160 RT       ",
                "model": {"model": "P0024_R000"},
            }
        )
        == DEVICE
    )


def test_raw_registers_win_over_null_or_stale_control_selection():
    dashboard = dashboard_fixture()
    groups(dashboard)[3]["selectedValue"] = "Low"
    state = parse_dashboard(DEVICE, dashboard)
    assert (state.speed, state.mode, state.filter_days) == (4, 0, 119)
    assert state.controls.boost_available


def test_hidden_stop_control_is_not_an_available_stop_capability():
    state = parse_dashboard(DEVICE, dashboard_fixture())
    assert state.controls.supports_stop is False
    with pytest.raises(UnsupportedDeviceError):
        build_command(state, state.controls.speed_group, "Parado")


def test_visible_enabled_stop_control_can_build_a_stop_command():
    dashboard = dashboard_fixture()
    groups(dashboard)[3]["sensors"][0]["isVisible"] = True
    state = parse_dashboard(DEVICE, dashboard)
    assert state.controls.supports_stop is True
    assert build_command(state, state.controls.speed_group, "Parado")["interaction"] == {
        "sensorGroupId": 20,
        "sensorId": "Parado",
        "sensorValueId": 0,
        "sensorGroupTypeId": 3,
        "fromSensorElementClassId": 47,
        "toSensorElementClassId": 47,
    }


@pytest.mark.parametrize("group_visible, option_state", [(False, 0), (True, -1)])
def test_disabled_stop_control_cannot_enable_stop(group_visible, option_state):
    dashboard = dashboard_fixture()
    groups(dashboard)[3]["isVisible"] = group_visible
    groups(dashboard)[3]["sensors"][0]["isVisible"] = True
    groups(dashboard)[3]["sensors"][0]["state"] = option_state
    state = parse_dashboard(DEVICE, dashboard)
    assert state.controls.supports_stop is False


def test_missing_raw_reading_is_unknown_not_derived_from_control():
    dashboard = dashboard_fixture()
    groups(dashboard).pop(4)
    groups(dashboard)[3]["selectedValue"] = "Low"
    assert parse_dashboard(DEVICE, dashboard).speed is None


@pytest.mark.parametrize("raw", ["1.0", "1e0", "NaN", "1oops", True])
def test_non_integer_raw_register_is_unknown_rather_than_coerced(raw):
    dashboard = dashboard_fixture()
    groups(dashboard)[4]["sensors"][0]["valueRaw"] = raw
    assert parse_dashboard(DEVICE, dashboard).speed is None


def test_duplicate_raw_register_disagreement_is_rejected():
    dashboard = dashboard_fixture()
    duplicate = copy.deepcopy(groups(dashboard)[4])
    duplicate["sensors"][0]["valueRaw"] = 2
    groups(dashboard).append(duplicate)
    with pytest.raises(ProtocolError):
        parse_dashboard(DEVICE, dashboard)


def test_low_command_preserves_all_invisible_coupled_groups():
    state = parse_dashboard(DEVICE, dashboard_fixture())
    assert build_command(state, state.controls.speed_group, "Speed1de4") == {
        "interaction": {
            "sensorGroupId": 20,
            "sensorId": "Speed1de4",
            "sensorValueId": 0,
            "sensorGroupTypeId": 3,
            "fromSensorElementClassId": 47,
            "toSensorElementClassId": 126,
        },
        "sensorGroups": [
            {
                "sensorGroupId": 10,
                "sensorsGroupElementList": [
                    {"sensorElementClassId": 32, "lastValue": 0, "selected": 1, "fromSelected": 0},
                    {"sensorElementClassId": 56, "lastValue": 0, "selected": 0, "fromSelected": 0},
                ],
            },
            {
                "sensorGroupId": 11,
                "sensorsGroupElementList": [
                    {"sensorElementClassId": 28, "lastValue": 0, "selected": 0, "fromSelected": 0},
                ],
            },
            {
                "sensorGroupId": 12,
                "sensorsGroupElementList": [
                    {"sensorElementClassId": 200, "lastValue": 0, "selected": 1, "fromSelected": 0},
                ],
            },
        ],
    }


def test_parent_command_sets_matching_child_and_clears_previous_modes():
    state = parse_dashboard(DEVICE, dashboard_fixture())
    command = build_command(state, state.controls.manual_group, "ModoIAQ")
    assert command["interaction"] == {
        "sensorGroupId": 10,
        "sensorId": "ModoIAQ",
        "sensorValueId": 1,
        "sensorGroupTypeId": 4,
        "fromSensorElementClassId": 32,
        "toSensorElementClassId": 56,
    }
    assert command["sensorGroups"] == [
        {
            "sensorGroupId": 10,
            "sensorsGroupElementList": [
                {"sensorElementClassId": 32, "lastValue": 1, "selected": 0, "fromSelected": 1},
                {"sensorElementClassId": 56, "lastValue": 1, "selected": 1, "fromSelected": 0},
            ],
        },
        {
            "sensorGroupId": 11,
            "sensorsGroupElementList": [
                {"sensorElementClassId": 28, "lastValue": 1, "selected": 1, "fromSelected": 0},
            ],
        },
        {
            "sensorGroupId": 12,
            "sensorsGroupElementList": [
                {"sensorElementClassId": 200, "lastValue": 0, "selected": 0, "fromSelected": 1},
            ],
        },
    ]


def test_unknown_model_is_not_assumed_compatible():
    with pytest.raises(UnsupportedDeviceError):
        parse_dashboard(Device("demo", "Unknown", "OTHER", True), dashboard_fixture())


def test_conflicting_live_speed_groups_fail_instead_of_picking_one():
    dashboard = dashboard_fixture()
    duplicate = copy.deepcopy(groups(dashboard)[3])
    duplicate["id"] = 21
    groups(dashboard).append(duplicate)
    with pytest.raises(UnsupportedDeviceError):
        parse_dashboard(DEVICE, dashboard)


def test_holiday_popup_speed_group_is_not_a_live_manual_control():
    dashboard = dashboard_fixture()
    holiday_group = copy.deepcopy(groups(dashboard)[3])
    holiday_group["isVisible"] = False
    holiday_group["dashboardPageId"] = 48
    dashboard["dashboardSections"][0]["frameZoneTypes"].append(
        {
            "id": 2,
            "dashboardName": "HolidayMode",
            "sensorGroupContainers": [{"id": 2, "sensorGroups": [holiday_group]}],
        }
    )
    assert parse_dashboard(DEVICE, dashboard).controls.speed_group["id"] == 20


def test_disabled_speed_is_rejected_before_building_a_command():
    dashboard = dashboard_fixture()
    groups(dashboard)[3]["sensors"][1]["state"] = -1
    state = parse_dashboard(DEVICE, dashboard)
    with pytest.raises(UnsupportedDeviceError):
        build_command(state, state.controls.speed_group, "Speed1de4")


def test_command_uses_runtime_raw_value_and_current_selected_class():
    dashboard = dashboard_fixture()
    groups(dashboard)[3]["selectedValue"] = "High"
    groups(dashboard)[3]["sensors"][1]["valueRaw"] = 7
    state = parse_dashboard(DEVICE, dashboard)
    assert build_command(state, state.controls.speed_group, "Speed1de4")["interaction"] == {
        "sensorGroupId": 20,
        "sensorId": "Speed1de4",
        "sensorValueId": 7,
        "sensorGroupTypeId": 3,
        "fromSensorElementClassId": 130,
        "toSensorElementClassId": 126,
    }


def test_unknown_coupled_selection_cannot_be_silently_cleared():
    dashboard = dashboard_fixture()
    groups(dashboard)[2]["selectedValue"] = "Unknown choice"
    state = parse_dashboard(DEVICE, dashboard)
    with pytest.raises(ProtocolError):
        build_command(state, state.controls.speed_group, "Speed1de4")
