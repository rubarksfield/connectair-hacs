# Scheduling and sensor limits

Two native Home Assistant schedule automations have been created, validated and enabled. Manually invoked runs of the current overnight rule completed with **both units reporting 100% in Manual mode**. Actual future 08:00/22:00 clock-trigger execution remains unverified. The generic recipe below uses the existing Connectair cloud integration; `fan.ventilation_unit_1` and `fan.ventilation_unit_2` are placeholders. These documentation changes do not change runtime version **0.1.1**.

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

The inspected dashboard update adds reported fan percentage/status and a capability-aware Turn off card for each unit. When TURN_OFF is absent, the card displays **Standby unavailable / Disabled** and has no tap action. It calls `fan.turn_off` only when TURN_OFF is present and the fan reports `on`; `off`, `unknown` and `unavailable` states have no tap action. Sixteen synthetic capability/state cases passed, and the saved configuration was read back with exactly four appended cards while existing cards were preserved. Those cards and the dedicated ventilation view were visually checked in the native desktop Home Assistant app. The ventilation view showed both units at 100%, Manual and Connected, with both schedule automations on. Phone rendering was not checked. No measured-humidity value or chart was added.

Configuration readback proves that a dashboard was saved. It does not prove that a time trigger fired or that the motor responded. Schedule validation covered 20 native-evaluator contexts and seven time-edge checks; the generic YAML also passed Home Assistant 2026.9.2 automation/action schemas. Both manually invoked overnight runs finished, neither automation remained active, and both fans reported on at 100% in Manual mode. One initial manual application failed; a later explicit manual application succeeded after fresh state and no active earlier run were confirmed. This was an operator action, not an automatic retry.

Actual 08:00/22:00 clock-trigger execution and physical motor response have not been observed. Validate the scheduled boundary, automation trace, reported mode/speed, startup behavior and physical response separately. Desktop visual verification does not establish phone rendering.

## Genuine Stop is conditional

In the inspected installation, both native fans lacked TURN_OFF and all five historical cloud dashboard responses hid the `Parado`/Stop option. The integration exposes OFF only when a fresh dashboard makes that option visible and enabled, then requires reported speed zero. Hidden controls must not be bypassed.

The [unit manual, p50](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=50) assigns standby allowance to **SW4**: ON forbids standby; OFF allows it. **SW2 controls supply/extract direction.** Pages [52](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=52) and [57](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=57) document remote-controlled standby at 0 m³/h, displayed as `FL0`. Actual switch positions and the reason the cloud hides Stop remain unverified; do not change hardware to try this recipe. [Night mode, pp56–58](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=56), runs at minimum speed. No documented Holiday OFF alternative was established.

## Humidity: sensor presence is not a cloud reading

The [manufacturer manual, pp55–56](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=55), confirms a built-in humidity sensor used by automatic mode. Its presence does not prove the cloud exposes measured internal relative humidity.

No validated numeric internal RH field was identified in five captured dashboards or 25 historical device-detail responses. The inspected `IR6` field represents motor PWM, not RH. Neither sensitivity settings nor unrelated registers may populate a humidity sensor. A fresh `/basic` response has not been captured, so that payload remains an evidence gap; the negative historical review does not prove every vendor endpoint lacks a reading.

The [manual, p60](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=60), defines **C08** as internal humidity sensitivity and **C10** as external AIRSENS RH sensitivity, both settings from 1 to 5. These are not measured percentages. [Page 67](https://statics.solerpalau.com/media/import/documentation/Ins_NARAH_160_RT.pdf#page=67) lists input **30023** as the external AIRSENS probe value, interpreted using probe type **30022**; it is not the internal RH reading.

Expose a numeric RH value only after its source, units, scale and freshness are validated. When no valid reading exists, retain an unavailable state rather than substituting zero or a sensitivity setting. The inspected payloads were private evidence and are not published here.
