# Connectair HACS design

Deliver an unofficial Home Assistant integration for S&P NARAH 160 RT using the existing Wi-Fi boards and S&P HTTPS cloud API. Publish to the confirmed personal account `rubarksfield`, with an Add to HACS button, install on HA 2026.9.2, discover both units and create a Ventilation dashboard. The user authorized implementation, publication and installation.

## Architecture and scope

Standalone repository; `custom_components/connectair/` contains runtime code. Pure protocol parsing and command construction, async aiohttp cloud client, Auth0 token manager, HA config flow/coordinator/native fan entities, reported mode/speed/filter diagnostics and a responsive two-fan dashboard. No unrelated HA changes, router interception, firmware modification or extra hardware.

Four manual speeds map to 25/50/75/100%. Named speeds are not fan presets. Speed selection must select manual mode when necessary. Boost is a separate button only if supported. Account polling every 30 seconds; per-device serialized commands refresh the snapshot, check acknowledgement and poll raw report-state registers. Do not optimistically claim success or blindly retry writes. Unsupported units and offline units must fail clearly.

## Protocol contract

Base `https://spportalwebapp-pro.azurewebsites.net/api`. Async token provider signature `async_get_access_token(force_refresh: bool = False) -> str`.

`Device`: device_id, name, model, online. `DeviceState`: device, speed (`int | None`), mode (`int | None`), filter_days (`int | None`), dashboard and discovered controls.

`ConnectairClient(session, token_provider)` exposes `async_list_devices() -> list[Device]`, `async_get_state(device_id: str) -> DeviceState`, `async_set_speed(device_id: str, speed: int) -> DeviceState`; optional boost only when discovered. Typed exceptions distinguish authentication, transport, unsupported control and failed command confirmation.

The activator supplies six interaction fields plus current non-cloned type-4/type-8 snapshots including invisible groups. Low uses Speed1de4/class126, Medium129, High130, Extra High131; sensorValueId is 0 for this type-3 group. Derive group/option IDs from runtime metadata. HR4 reports speed, HR3 reports mode. Incomplete selectedValue controls must not overrule raw register readings or accidentally activate night/holiday/schedule/reset-filter actions.

## Authentication

Auth0 web client permits the refresh grant and rejects password grant. Real refresh issuance still needs verification. Use authorization code plus PKCE with the provider-approved callback `https://www.connectairapp.com` and state validation. Query versus fragment response mode is under live verification: the vendor SDK navigates away from foreign query transactions. A callback-URL relay into the HA config flow is needed because arbitrary HA callbacks are not registered. Request offline_access only at the authorized persistent-login step. Never claim unattended renewal until a real refresh succeeds.

Tokens and PKCE secrets remain in HA private memory/config-entry storage, never GitHub/logs/diagnostics. TLS validation enabled. Refresh rotation persists immediately with a lock. Expired/revoked login triggers reauth. Account identity comes from `/user/me`, not unverified JWT claims. Missing refresh tokens must be surfaced honestly.

## Completion evidence

Protocol/auth/HA tests and lint pass; independent authenticated control and refresh succeed; reviewed reusable repository published to rubarksfield; HACS installation read back; both native entities available; HA command changes Studio and reported state agrees; dashboard renders using exact live entities. Each unverified stage remains explicitly incomplete.
