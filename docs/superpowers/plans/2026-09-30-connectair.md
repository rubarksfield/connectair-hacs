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
G2 auth active: refresh grant allowed, password rejected; actual PKCE relay and refresh proof pending renewable-access confirmation.
G3 implementation complete: protocol/auth/HA adapter, packaging and CI implemented.
G4 automated verification complete: 108 tests pass against genuine HA 2026.9.2; ruff checks and formatting pass; independent review fixes applied including conditional Stop capability. Live authentication remains a release gate.
G5 publish/install/dashboard pending; personal account confirmed rubarksfield and already authenticated locally.
G6 completion review pending.
