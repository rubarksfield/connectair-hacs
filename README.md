# S&P Connectair for Home Assistant

Control S&P NARAH ventilation through its existing Connectair Wi-Fi connection. No additional Modbus adapter is required.

**Version 0.1.1:** real PKCE sign-in, refresh-token renewal, independent device control and live Home Assistant enrollment have been verified. Two NARAH 160 RT units were discovered; a Home Assistant Medium-to-Low control test completed against reported speed registers. This patch protects formatted error tracebacks from underlying private provider details. Automated tests run against Home Assistant 2026.9.2.

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rubarksfield&repository=connectair-hacs&category=integration)
[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=connectair)

This is an independent community integration, unaffiliated with S&P. It uses the Connectair cloud service; an internet connection and a working S&P account are required. Local, offline control is not implemented. See the [LAN control investigation](docs/lan-control.md) for verified findings and the next capture step.

Changes and implementation findings are recorded in the [changelog](CHANGELOG.md).

## Features

- Automatically discovers the units linked to your Connectair account.
- Native fan entities: Low (25%), Medium (50%), High (75%) and Extra High (100%). Setting a speed selects a supported manual mode when needed. Stop/0% is available only when the unit exposes an enabled Stop control.
- Reported speed, operating mode, filter replacement countdown and connectivity sensors.
- Reads every 30 seconds. Commands are serialized per unit and confirmed using reported registers before Home Assistant shows success. Cloud delivery or status reporting may take several minutes; each acknowledged command has a three-minute confirmation deadline. If confirmation times out, the command may still arrive later; check the reported state before retrying.
- Renewable sign-in, refresh-token rotation and Home Assistant reauthentication.
- Diagnostics omit account identifiers, device identifiers, names, raw dashboards and credentials.

Initially supports NARAH 160 RT/P0024_R000 controls. Other models require explicit validation and are currently rejected. Boost and automatic-mode controls are not exposed in this version.

## Install

Requires Home Assistant **2026.9.2 or newer** and HACS.

1. Use **Add to HACS** above, or add `https://github.com/rubarksfield/connectair-hacs` under HACS → Custom repositories, category **Integration**.
2. Download **S&P Connectair** and restart Home Assistant.
3. Open Settings → Devices & services → Add integration → **S&P Connectair**.
4. Follow the sign-in link in a new tab. Sign in to your existing S&P account and allow renewable access. Copy the complete returned Connectair address containing the `code=` and `state=` query parameters, and paste it into the integration form. If S&P shows an **Auth Error** page, open your browser history and copy the preceding Connectair address containing `code=` and `state=`. The error-page address will not work. Keep the callback address private: it contains a one-time login code.
5. The integration verifies token renewal and your account before adding devices. Assign each device to its room.

S&P only registers its own callback address for the existing app client. This integration uses a PKCE-protected query callback relay instead of requesting your account password. A real authorization-code exchange, refresh-token issuance and subsequent refresh have been verified with S&P. Fragment callbacks are rejected by the provider, so use the complete query callback address described above. If S&P does not issue renewable credentials, setup fails with an authentication error. Do not share callback addresses or tokens in issues.

For advanced setup, an optional **Refresh token (advanced)** field accepts a private refresh token already issued for your Connectair account. Leave the callback address blank when using this option. The field masks the credential; the integration renews it, verifies the account and stores the returned token bundle in Home Assistant's private configuration. Leave this field blank for normal sign-in. It accepts a refresh token, not your S&P password.

## Dashboard and automations

See the [daily scheduling and sensor guide](docs/scheduling-and-sensors.md) for a maximum-speed overnight schedule, manual overrides, capability-aware Off buttons and the current limits on measured humidity.

Use Home Assistant Tile cards for status, with separate speed buttons for **25%, 50%, 75% and 100%**. The native fan-speed slider includes 0%, which is unsupported on units without Stop. Set tile and icon taps to **More info** when Stop is unavailable. The native fan entities work with normal actions, for example:

```yaml
action: fan.set_percentage
target:
  entity_id: fan.your_connectair_unit
data:
  percentage: 25
```

Replace the example entity ID with the actual discovered entity. The integration preserves unrelated settings in S&P's coupled control payload. An offline unit, unknown operating mode or unsupported control response raises an error instead of inventing a successful state.

## Troubleshooting

- **Login expired:** use the reauthentication prompt in Devices & services.
- **Auth Error after signing in:** retrieve the preceding Connectair callback address from browser history, including `code=` and `state=`, and paste it into the Home Assistant form. If the code has expired, start a fresh sign-in using the form's link.
- **Unit unavailable:** confirm it is online in Connectair and that Home Assistant can reach the internet.
- **Command unconfirmed:** check the fan in the S&P app. An acknowledgement without updated reported registers is not treated as success; retry after reading its current state.
- **New model:** open an issue with the model and redacted integration diagnostics. Never attach raw HAR files, login URLs or credentials.

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
