# Scheduling and sensor limits

Two native Home Assistant schedule automations have been created, validated and enabled. Manually invoked overnight runs completed with **both units reporting 100% in Manual mode**. The actual **08:00 Europe/Lisbon time triggers on 1 October** also completed, with both units subsequently reporting **25% in Manual mode**. The 22:00 clock trigger and physical motor response remain unverified. The generic recipe below uses the existing Connectair cloud integration; `fan.ventilation_unit_1` and `fan.ventilation_unit_2` are placeholders. Humidity support is added separately in runtime version **0.1.2**; the schedule rules are unchanged.

## Daily schedule for two units

Apply the following rule every day in Home Assistant's configured local timezone:

| Period | Requested speed |
| --- | --- |
| 22:00, inclusive, to 08:00, exclusive | 100%: Super high, level 4 |
| 08:00, inclusive, to 22:00, exclusive | 25%: Low, level 1 |

Create one automation per unit in **Settings → Automations & scenes**. Separate automations let one unavailable unit fail without preventing the other unit's scheduled action.

| Automation setting | Generic configuration |
| --- | --- |
| Target | One placeholder fan entity, replaced with the actual entity selected in the UI |
| Time triggers | 22:00 and 08:00; give these boundary triggers an identifiable ID |
| Startup trigger | Home Assistant starts |
| Other triggers | None: no reconnect, availability or percentage-change triggers |
| Mode | `queued`, maximum 2 runs |
| Readiness wait | Wait up to five minutes for the fan to report `on` or `off`; continue immediately if already ready, otherwise stop on timeout |
| Startup guard | At startup, continue only when the fan reports `on`; preserve reported Off |
| Time choice | A native Time condition with After 22:00 and Before 08:00 |
| Night action | `fan.set_percentage`, percentage 100, targeting this unit |
| Default action | `fan.set_percentage`, percentage 25, targeting this unit |

Evaluate readiness and the current time inside the action sequence, so a queued run does not apply a period that has already ended. Skip a write when the unit is already on at the requested percentage. Home Assistant's [Time condition](https://www.home-assistant.io/docs/scripts/conditions/#time-condition) supports windows crossing midnight, with an inclusive start and exclusive end. The action is the native [Set fan speed action](https://www.home-assistant.io/integrations/fan/#list-of-actions).

### Generic automation configuration

Use the automation editor or config API rather than editing Home Assistant's internal storage. This complete example targets the first placeholder unit. Create a second copy with a distinct ID/alias and replace **every** `fan.ventilation_unit_1` with `fan.ventilation_unit_2`. The only template is the required level check: a change-only wait would miss an already-ready fan.

```yaml
id: ventilation_unit_1_daily_schedule
alias: Ventilation unit 1 daily schedule
mode: queued
max: 2
triggers:
  - trigger: time
    at: "22:00:00"
    id: boundary
  - trigger: time
    at: "08:00:00"
    id: boundary
  - trigger: homeassistant
    event: start
    id: startup
actions:
  - wait_template: "{{ states('fan.ventilation_unit_1') in ['on', 'off'] }}"
    timeout: "00:05:00"
    continue_on_timeout: false
  - condition: or
    conditions:
      - condition: trigger
        id: boundary
      - condition: state
        entity_id: fan.ventilation_unit_1
        state: "on"
  - choose:
      - conditions:
          - condition: time
            after: "22:00:00"
            before: "08:00:00"
        sequence:
          - condition: not
            conditions:
              - condition: and
                conditions:
                  - condition: state
                    entity_id: fan.ventilation_unit_1
                    state: "on"
                  - condition: state
                    entity_id: fan.ventilation_unit_1
                    attribute: percentage
                    state: 100
          - action: fan.set_percentage
            target:
              entity_id: fan.ventilation_unit_1
            data:
              percentage: 100
    default:
      - condition: not
        conditions:
          - condition: and
            conditions:
              - condition: state
                entity_id: fan.ventilation_unit_1
                state: "on"
              - condition: state
                entity_id: fan.ventilation_unit_1
                attribute: percentage
                state: 25
      - action: fan.set_percentage
        target:
          entity_id: fan.ventilation_unit_1
        data:
          percentage: 25
```

The five-minute wait checks reported state; it does not send a command. If readiness is not established within that window, skip the run until the next time boundary or Home Assistant restart. There are no automatic retries or reconnect triggers. This avoids an availability flap triggering another write after an earlier acknowledged command failed to confirm.

## Manual overrides and startup

A manual speed change lasts until the next 22:00 or 08:00 boundary. Do not trigger this automation on percentage changes or on every cloud poll: that would immediately overwrite the user's choice. At a boundary, an available unit resumes the scheduled speed, including a previously reported Off unit where genuine Stop is supported.

Startup is a separate rule: after the bounded readiness wait, apply the current period only to units reporting `on`. Preserve a reported Off state. A startup run can replace a manual speed override on a running unit; disable its schedule automation when a longer override is needed. Manual Off-to-On changes and reconnects do not trigger this schedule.

Use [queued mode](https://www.home-assistant.io/docs/automation/modes/) so another trigger waits for an in-flight action. `restart` would cancel the existing run, potentially interrupting confirmation after the cloud has already acknowledged the command. Acknowledgement does not establish when the motor changed speed; status can arrive later. An acknowledged write must not be replayed merely because its confirmation was cancelled or delayed.

## Dashboard controls and verification

For each unit, show reported speed, operating mode, connectivity and filter countdown alongside four explicit **25%, 50%, 75% and 100%** actions. Show the schedule's enabled state so users can pause it. Avoid an unrestricted slider reaching 0% or a power toggle when TURN_OFF is unavailable.

Before the 0.1.2 humidity update, the inspected dashboard update added reported fan percentage/status and a capability-aware Turn off card for each unit. When TURN_OFF is absent, the card displays **Standby unavailable / Disabled** and has no tap action. It calls `fan.turn_off` only when TURN_OFF is present and the fan reports `on`; `off`, `unknown` and `unavailable` states have no tap action. Sixteen synthetic capability/state cases passed, and the saved configuration was read back with exactly four appended cards while existing cards were preserved. Those cards and the dedicated ventilation view were visually checked in the native desktop Home Assistant app. The ventilation view showed both units at 100%, Manual and Connected, with both schedule automations on. Phone rendering was not checked. No measured-humidity value or chart was added at that earlier stage; those visual checks do not verify the later humidity dashboard changes.

Configuration readback proves that a dashboard was saved. It does not prove that a time trigger fired or that the motor responded. Schedule validation covered 20 native-evaluator contexts and seven time-edge checks; the generic YAML also passed Home Assistant 2026.9.2 automation/action schemas. Both manually invoked overnight runs finished, neither automation remained active, and both fans reported on at 100% in Manual mode. One initial manual application failed; a later explicit manual application succeeded after fresh state and no active earlier run were confirmed. This was an operator action, not an automatic retry.

At 08:00 Europe/Lisbon on 1 October, both genuine time-triggered traces selected the daytime action, issued exactly one `fan.set_percentage: 25` per unit and finished without trace errors. At 08:01:30, both units reported on at 25%, speed level 1 and Manual mode, with neither automation still running. This verifies scheduled execution and cloud-reported state, not the time or fact of physical motor actuation. The 22:00 clock trigger, startup behavior and physical response still require separate live verification. Desktop visual verification does not establish phone rendering.

## Genuine Stop is conditional

In the inspected installation, both native fans lacked TURN_OFF and all five historical cloud dashboard responses hid the `Parado`/Stop option. The integration exposes OFF only when a fresh dashboard makes that option visible and enabled, then requires reported speed zero. Hidden controls must not be bypassed.

The [unit manual, p50](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=50) assigns standby allowance to **SW4**: ON forbids standby; OFF allows it. **SW2 controls supply/extract direction.** Pages [52](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=52) and [57](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=57) document remote-controlled standby at 0 m³/h, displayed as `FL0`. Actual switch positions and the reason the cloud hides Stop remain unverified; do not change hardware to try this recipe. [Night mode, pp56–58](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=56), runs at minimum speed. No documented Holiday OFF alternative was established.

## Cloud-reported humidity

The [manufacturer manual, pp55–56](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=55), confirms a built-in humidity sensor used by automatic mode. Its presence does not prove the cloud exposes measured internal relative humidity.

During the initial investigation, no validated numeric internal RH field was identified in five captured dashboards or 25 historical device-detail responses. The inspected `IR6` field represents motor PWM, not RH. Neither sensitivity settings nor unrelated registers may populate a humidity sensor. On 1 October, five fresh authenticated GETs returned the device list, both `/basic` responses and both full details successfully; none contained humidity or temperature readings. This closed the fresh-basic evidence gap for those endpoints. The separate measurement source was identified later, as described below.

The later [executable native-app trace](lan-control.md#executable-direct-wi-fi-and-measurement-trace) identified a separate cloud GET `/device/{id}/state`. Its `reading.ambientHumidity` passes through the app's parser and equipment callback to a percentage display. Fresh authenticated responses for both owned NARAH units contained numeric humidity with matching `status.deviceId` and `status.isOnline: true`. This establishes a cloud-reported RH source; earlier list/basic/detail/dashboard reads did not use this endpoint.

Version **0.1.2** adds a native **Humidity** sensor per supported unit. It uses `SensorDeviceClass.HUMIDITY`, percent units and `SensorStateClass.MEASUREMENT`, allowing normal Home Assistant history and statistics. A separate 30-second coordinator reads measurements without adding requests to fan commands or their confirmation loop. Humidity transport/protocol failures affect the humidity entity, while fan polling and commands retain their existing behavior.

On 1 October, version **0.1.2** was installed through HACS and Home Assistant Core was restarted. Both discovered humidity entities subsequently reported updating numeric percentages with native humidity, percent and measurement metadata; both fans continued to report 25%. One humidity entity was initially unavailable, then recovered during an ordinary scheduled poll. Its fresh cloud measurement response had matching identity, online status and a valid numeric percentage. The initial unavailable state's cause was not established, and no runtime fix was applied.

Recorder history returned multiple changing numeric samples for both sensors after installation. The ventilation dashboard now has one live humidity tile and one 24-hour history graph per unit; the home dashboard has one live humidity figure per unit. Saved configuration readback confirmed four ventilation additions and two home additions, with previous content preserved. Both live ventilation readings and humidity graphs were visually verified in the native desktop Home Assistant app. The desktop view became unavailable before the home humidity figures could be visually confirmed; their saved configuration and underlying sensor readings were checked. The graphs start with newly recorded samples, so a full day of humidity history is not yet available. Both fans remained at 25% and their schedule automations remained enabled with idle queues. Long-term statistics and phone rendering were not verified. Local/offline fan control remains unproven.

Only finite numeric values from 0 through 100 are accepted, with no scaling. Booleans, numeric strings, missing/null values and invalid ranges are unavailable; offline reports and mismatched device identities are not used. The app's humidity status values select comfort icons rather than a proven validity flag, so status 1 or 2 does not invalidate a numeric reading. No sensitivity or PWM setting supplies this sensor.

The cloud response provides no hardware measurement timestamp. Poll receipt time establishes when Home Assistant obtained a response, not the age or calibration of the device's sample. Physical humidity calibration remains unverified, and the sensor still requires the Connectair cloud.

Add the actual discovered humidity entity to a Tile card for the live figure. A native [history graph](https://www.home-assistant.io/dashboards/history-graph/) can show the last 24 hours; data begins when the sensor is installed, with no backfilled historical readings. For example, use the dashboard editor/API with the following generic card shape, replacing the placeholder entity:

```yaml
type: history-graph
title: Relative humidity · 24 hours
hours_to_show: 24
min_y_axis: 0
max_y_axis: 100
entities:
  - entity: sensor.your_connectair_unit_humidity
    name: Relative humidity
```

The [manual, p60](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=60), defines **C08** as internal humidity sensitivity and **C10** as external AIRSENS RH sensitivity, both settings from 1 to 5. These are not measured percentages. [Page 67](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=67) lists input **30023** as the external AIRSENS probe value, interpreted using probe type **30022**; it is not the internal RH reading.

When no valid reading exists, retain an unavailable state rather than substituting zero, a sensitivity setting or a previous successful value after a failed poll. The inspected payloads remain private and are not published here.
