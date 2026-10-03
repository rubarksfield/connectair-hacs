# 🌬️ S&P Connectair for Home Assistant

**A little breeze. A lot more control.**

Bring your S&P NARAH ventilation into Home Assistant: choose a speed, follow temperature and humidity, keep an eye on filters, and let your automations handle the routine. It works through your existing Connectair Wi-Fi connection.

[![HACS custom integration](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistant&logoColor=white)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![Latest release](https://img.shields.io/github/v/release/rubarksfield/home-assistant-connectair)](https://github.com/rubarksfield/home-assistant-connectair/releases/latest)
[![Tests](https://github.com/rubarksfield/home-assistant-connectair/actions/workflows/tests.yml/badge.svg)](https://github.com/rubarksfield/home-assistant-connectair/actions/workflows/tests.yml)
[![HACS and hassfest](https://github.com/rubarksfield/home-assistant-connectair/actions/workflows/validate.yml/badge.svg)](https://github.com/rubarksfield/home-assistant-connectair/actions/workflows/validate.yml)
[![Secret scan](https://github.com/rubarksfield/home-assistant-connectair/actions/workflows/secrets.yml/badge.svg)](https://github.com/rubarksfield/home-assistant-connectair/actions/workflows/secrets.yml)

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rubarksfield&repository=home-assistant-connectair&category=integration)
[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=connectair)

| Before you get breezy | What you need |
| --- | --- |
| Home Assistant | **2026.9.2 or newer**, with HACS installed |
| Ventilation | **S&P NARAH 160 RT**, using supported **P0024_R000** controls |
| Account and connection | Your existing S&P Connectair account and internet access |
| Installation | HACS **custom repository**, category **Integration** |

**Version 0.1.3** adds ambient temperature in °C alongside humidity. The integration provides normal Home Assistant entities for your dashboards, history and automations. See the [changelog](CHANGELOG.md) for release details.

This independent community integration is unaffiliated with S&P. It uses the **Connectair cloud**; local, offline control is not implemented. Other models need validation before they can be supported.

## Features

- Automatically discovers the units linked to your Connectair account.
- Native fan entities: Low (25%), Medium (50%), High (75%) and Extra High (100%). Setting a speed selects a supported manual mode when needed. Stop/0% is available only when the unit exposes an enabled Stop control.
- Reported speed, operating mode, filter replacement countdown, connectivity, relative-humidity and ambient-temperature sensors.
- Humidity and temperature are read together every 30 seconds. Each field is validated independently; missing, invalid or offline readings become unavailable without interrupting fan controls. Values are cloud-reported, have no hardware sample timestamp, and have not been physically calibrated.
- Reads every 30 seconds. Commands are serialized per unit and confirmed using reported registers before Home Assistant shows success. Cloud delivery or status reporting may take several minutes; each acknowledged command has a three-minute confirmation deadline. If confirmation times out, the command may still arrive later; check the reported state before retrying.
- Renewable sign-in, refresh-token rotation and Home Assistant reauthentication.
- Diagnostics omit account identifiers, device identifiers, names, raw dashboards and credentials.

Initially supports NARAH 160 RT/P0024_R000 controls. Other models require explicit validation and are currently rejected. Boost and automatic-mode controls are not exposed in this version.

## Install

Five steps to a smarter breeze.

Requires Home Assistant **2026.9.2 or newer** and HACS.

1. Use **Add to HACS** above. For a manual install, open HACS → ⋮ → **Custom repositories**, add `https://github.com/rubarksfield/home-assistant-connectair`, and choose **Integration**.
2. Download **S&P Connectair** and restart Home Assistant.
3. Open Settings → Devices & services → Add integration → **S&P Connectair**.
4. Follow the sign-in link in a new tab. Sign in to your existing S&P account and allow renewable access. Copy the complete returned Connectair address containing the `code=` and `state=` query parameters, and paste it into the integration form. If S&P shows an **Auth Error** page, open your browser history and copy the preceding Connectair address containing `code=` and `state=`. The error-page address will not work. Keep the callback address private: it contains a one-time login code.
5. The integration verifies your account and token renewal, then discovers your supported units. Assign them to their rooms and add their fan, temperature and humidity entities to a dashboard. You're ready to catch a breeze.

Already installed from `rubarksfield/connectair-hacs`? The old repository address redirects here. HACS can refresh the repository information to pick up the new name; your integration domain, entities and installed version do not change.

S&P only registers its own callback address for the existing app client. This integration uses a PKCE-protected query callback relay instead of requesting your account password. A real authorization-code exchange, refresh-token issuance and subsequent refresh have been verified with S&P. Fragment callbacks are rejected by the provider, so use the complete query callback address described above. If S&P does not issue renewable credentials, setup fails with an authentication error. Do not share callback addresses or tokens in issues.

For advanced setup, an optional **Refresh token (advanced)** field accepts a private refresh token already issued for your Connectair account. Leave the callback address blank when using this option. The field masks the credential; the integration renews it, verifies the account and stores the returned token bundle in Home Assistant's private configuration. Leave this field blank for normal sign-in. It accepts a refresh token, not your S&P password.

## Dashboard and automations

See the [daily scheduling and sensor guide](docs/scheduling-and-sensors.md) for a maximum-speed overnight schedule, manual overrides, capability-aware Off buttons, live humidity and temperature figures, and history charts.

Use Home Assistant Tile cards for status, with separate speed buttons for **25%, 50%, 75% and 100%**. The native fan-speed slider includes 0%, which is unsupported on units without Stop. Set tile and icon taps to **More info** when Stop is unavailable. The native fan entities work with normal actions, for example:

```yaml
action: fan.set_percentage
target:
  entity_id: fan.your_connectair_unit
data:
  percentage: 25
```

Replace the example entity ID with the actual discovered entity. The integration preserves unrelated settings in S&P's coupled control payload. An offline unit, unknown operating mode or unsupported control response raises an error instead of inventing a successful state.

## Help wanted: local control

The integration currently depends on Connectair's cloud service. No reliable board-local fan command, status read or offline-control path has been demonstrated. The [LAN investigation](docs/lan-control.md) records tested listeners, encrypted traffic and the separate documented Modbus route; an Espressif chip alone does not imply ESPHome or another standard control API.

Contributions are welcome from people familiar with S&P NARAH, ESP32 networking, TLS or Modbus. A useful issue or pull request should provide reproducible, redacted evidence for a local status read and, ideally, a speed command with reported-state confirmation. Please do not post credentials, sign-in callback URLs, registration keys, device/account identifiers, household IP or MAC addresses, raw packet captures, HAR files or private Home Assistant configuration. Keep firmware changes and hardware wiring out of scope unless their risks and rollback are documented.

## Troubleshooting

- **Login expired:** use the reauthentication prompt in Devices & services.
- **Auth Error after signing in:** retrieve the preceding Connectair callback address from browser history, including `code=` and `state=`, and paste it into the Home Assistant form. If the code has expired, start a fresh sign-in using the form's link.
- **Unit unavailable:** confirm it is online in Connectair and that Home Assistant can reach the internet.
- **Command unconfirmed:** check the fan in the S&P app. An acknowledgement without updated reported registers is not treated as success; retry after reading its current state.
- **New model:** open an issue with the model and redacted integration diagnostics. Never attach raw HAR files, login URLs or credentials.

Still stuck? [Report a bug](https://github.com/rubarksfield/home-assistant-connectair/issues/new?template=bug_report.yml) or [suggest an improvement](https://github.com/rubarksfield/home-assistant-connectair/issues/new?template=feature_request.yml). Share what happened, the model and software versions; keep account and household details private.

## Development

Tests run against genuine Home Assistant 2026.9.2 on Python 3.14.2:

```sh
uv sync --frozen
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Test fixtures contain synthetic data. A small fixture adapts aioresponses 0.7's response constructor to aiohttp 3.14; production HTTP behavior is unchanged.

Before publishing changes, follow [repository maintenance and privacy rules](AGENTS.md), update the changelog, and scan both Git history and staged changes with Gitleaks 8.30.1. CI scans full fetched history with redacted output. Keep real credentials, callback URLs, pairing keys and captures out of the repository. See the [publication privacy audit](docs/privacy-audit.md) for inspected surfaces, results and limitations.

Repository layout follows [HACS integration requirements](https://www.hacs.dev/docs/publish/integration/). Brand assets are bundled using [Home Assistant's custom integration support](https://developers.home-assistant.io/docs/core/integration/brand_images/).

MIT license. S&P and Connectair names remain their respective owners' trademarks.
