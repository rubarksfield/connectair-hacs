# S&P Connectair for Home Assistant

Control S&P NARAH ventilation through its existing Connectair Wi-Fi connection. No additional Modbus adapter is required.

**Development preview:** automated checks pass against Home Assistant 2026.9.2. Live renewable sign-in and unattended control are still being verified. There is no production release yet.

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=rubarksfield&repository=connectair-hacs&category=integration)
[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=connectair)

This is an independent community integration, unaffiliated with S&P. It uses the Connectair cloud service; an internet connection and a working S&P account are required. Local, offline control is not implemented.

## Features

- Automatically discovers the units linked to your Connectair account.
- Native fan entities: Low (25%), Medium (50%), High (75%) and Extra High (100%). Setting a speed selects a supported manual mode when needed. Stop/0% is available only when the unit exposes an enabled Stop control.
- Reported speed, operating mode, filter replacement countdown and connectivity sensors.
- Reads every 30 seconds. Commands are serialized per unit and confirmed using reported registers before Home Assistant shows success.
- Renewable sign-in, refresh-token rotation and Home Assistant reauthentication.
- Diagnostics omit account identifiers, device identifiers, names, raw dashboards and credentials.

Initially supports NARAH 160 RT/P0024_R000 controls. Other models require explicit validation and are currently rejected. Boost and automatic-mode controls are not exposed in this version.

## Install

Requires Home Assistant **2026.9.2 or newer** and HACS.

1. Use **Add to HACS** above, or add `https://github.com/rubarksfield/connectair-hacs` under HACS → Custom repositories, category **Integration**.
2. Download **S&P Connectair** and restart Home Assistant.
3. Open Settings → Devices & services → Add integration → **S&P Connectair**.
4. Follow the sign-in link. Sign in to your existing S&P account and allow renewable access. Paste the complete returned Connectair address into the integration form. The address contains a one-time code; keep it private. The callback relay is currently under live verification; S&P's web app may navigate away before the returned address can be copied.
5. The integration verifies token renewal and your account before adding devices. Assign each device to its room.

S&P only registers its own callback address for the existing app client. This integration uses a PKCE-protected callback relay instead of requesting your account password. If S&P does not issue renewable credentials, setup fails with an authentication error. Do not share callback addresses or tokens in issues.

## Dashboard and automations

Add the fan entities to a Home Assistant Tile card with the **Fan speed** feature. The native fan entities work with normal actions, for example:

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

Repository layout follows [HACS integration requirements](https://www.hacs.dev/docs/publish/integration/). Brand assets are bundled using [Home Assistant's custom integration support](https://developers.home-assistant.io/docs/core/integration/brand_images/).

MIT license. S&P and Connectair names remain their respective owners' trademarks.
