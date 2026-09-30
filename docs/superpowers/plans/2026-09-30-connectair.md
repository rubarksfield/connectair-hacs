# Connectair HACS Implementation Plan

> **For agentic workers:** Root execution with parallel independent protocol/auth/review tasks. Preserve the user's full implementation/publication/install authorization.

**Goal:** Reusable HACS integration, installed devices and a live Ventilation dashboard.

**Architecture:** Pure protocol plus async cloud client, renewable Auth0 token manager, HA config flow/coordinator/entities and native dashboard.

**Tech Stack:** Python 3.14.2, aiohttp, HA 2026.9.2, pytest, ruff, HACS, GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-09-30-connectair-design.md`

## Global constraints

- Standard TLS; no credentials or household IDs in public repository.
- Fail explicitly for unsupported/offline units; preserve unrelated settings.
- Standalone auth/control, HACS installation and device readback are separate gates.

## Review focus

- Ambiguous selections must not corrupt snapshots.
- Refresh rotation/concurrent calls must not lose tokens.
- Offline/unsupported devices must not expose invented capabilities.
- Rejected/time-out commands must not report success.
- Diagnostics and errors must redact credentials/account data.

### Task 1: Protocol/client

Files: api.py, models.py, tests/test_api.py, tests/test_models.py.
Interfaces: Device/DeviceState and async token/provider methods from spec.
- [ ] Write and run failing literal-fixture tests: raw registers, missing selections, snapshot preservation, unsupported data and command confirmation.
- [ ] Implement exact current app protocol and client; distinguish errors; pass targeted tests.
- [ ] Exercise HTTP boundary success/auth/timeout/malformed responses; run lint.

### Task 2: Auth/config flow

Files: auth.py, config_flow.py, tests/test_auth.py, tests/test_config_flow.py.
- [ ] Pin PKCE, callback host/state validation, expiry/concurrency, rotation and safe errors in failing tests.
- [ ] Implement authorize/exchange/refresh and account validation with reauth.
- [ ] Verify actual code exchange, refresh and standalone control; no guessed persistent auth.

### Task 3: HA/package

Files: __init__.py, coordinator.py, fan.py, sensor.py, binary_sensor.py, button.py, const.py, manifest.json, strings.json, translations/en.json, diagnostics.py; HACS/README/license/CI.
- [ ] Test percentages, availability, command routing, unload, duplicate account and redaction before implementation.
- [ ] Implement current HA lifecycle/platforms; add personal-owner HACS button.
- [ ] Run entire pytest suite, ruff, metadata validation; fresh review and targeted fixes.

### Task 4: Publish/install/dashboard

- [ ] Publish reviewed source/release to rubarksfield; add/download through HACS; verify files/version.
- [ ] Validate HA config and perform authorized integration restart.
- [ ] Authenticate/configure through HA flow; read back both entities and an HA command.
- [ ] Create Ventilation dashboard via HA API with exact entities; render/inspect.

## Goal ledger

G1 inspection complete: command source/normal-app physical test, HA 2026.9.2 and HACS live.
G2 auth verified: user explicitly authorized private renewable-token storage in HA. Real query-PKCE exchange and refresh grant succeeded; account validation and both device reads succeeded after proving the server requires the official app Origin header. Fragment authorization fails at the provider. Browser history preserves the query callback when the app routes it to Auth Error.
G3 implementation complete: protocol/auth/HA adapter, packaging and CI implemented.
G4 automated verification complete: 152 tests pass against genuine HA 2026.9.2; full Ruff lint and formatting pass. Exact repeated cloud records are normalized without hiding conflicting metadata. A masked refresh-token field supports private account enrollment; transient account verification can reuse a rotated token in flow memory. Confirmation is bounded by 31 reads, 3-second intervals and a 90-second deadline, tolerating temporary offline reports only after acknowledgement. Commands are never replayed.
G5 active: development preview published to rubarksfield/connectair-hacs, installed through HACS and restarted. Independent Origin-only Medium-to-Low control is now verified: reported speed and actual RPM agree. Delivery took over a minute and briefly reported offline, explaining the earlier unconfirmed result. Studio was restored to Low/manual; Workshop was untouched. Final runtime fixes need publishing/installing, followed by private account enrollment, both device entries, a Home Assistant control test and dashboard readback.
G6 completion review pending.

### Task 5: LAN control research (after current setup is complete)

- [ ] Research local control using the existing Espressif Wi-Fi boards, with no additional hardware.
- [ ] Inspect documented local protocols, the app's network behavior, local services and supported device commands.
- [ ] Distinguish a proven offline control path from provisioning-only endpoints and cloud traffic.
- [ ] Report a recommended path, evidence, limitations and a reversible proof-of-concept plan. Research does not authorize firmware flashing or changing network isolation.
