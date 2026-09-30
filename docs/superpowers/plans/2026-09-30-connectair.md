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
- [x] Write and run failing literal-fixture tests: raw registers, missing selections, snapshot preservation, unsupported data and command confirmation.
- [x] Implement exact current app protocol and client; distinguish errors; pass targeted tests.
- [x] Exercise HTTP boundary success/auth/timeout/malformed responses; run lint.

### Task 2: Auth/config flow

Files: auth.py, config_flow.py, tests/test_auth.py, tests/test_config_flow.py.
- [x] Pin PKCE, callback host/state validation, expiry/concurrency, rotation and safe errors in failing tests.
- [x] Implement authorize/exchange/refresh and account validation with reauth.
- [x] Verify actual code exchange, refresh and standalone control; no guessed persistent auth.

### Task 3: HA/package

Files: __init__.py, coordinator.py, fan.py, sensor.py, binary_sensor.py, button.py, const.py, manifest.json, strings.json, translations/en.json, diagnostics.py; HACS/README/license/CI.
- [x] Test percentages, availability, command routing, unload, duplicate account and redaction before implementation.
- [x] Implement current HA lifecycle/platforms; add personal-owner HACS button.
- [x] Run entire pytest suite, ruff, metadata validation; fresh review and targeted fixes.

### Task 4: Publish/install/dashboard

- [x] Publish reviewed source/release to rubarksfield; add/download through HACS; verify files/version.
- [x] Validate HA config and perform authorized integration restart.
- [x] Authenticate/configure through HA flow; read back both entities and an HA command.
- [x] Create Ventilation dashboard via HA API with exact entities; verify full saved configuration and restart persistence.
- [ ] Render/inspect dashboard: blocked by disabled screenshot support and unavailable authenticated browser preview; disclose this verification limit.

## Goal ledger

G1 inspection complete: command source/normal-app physical test, HA 2026.9.2 and HACS live.
G2 auth verified: user explicitly authorized private renewable-token storage in HA. Real query-PKCE exchange and refresh grant succeeded; account validation and both device reads succeeded after proving the server requires the official app Origin header. Fragment authorization fails at the provider. Browser history preserves the query callback when the app routes it to Auth Error.
G3 implementation complete: protocol/auth/HA adapter, packaging and CI implemented.
G4 automated verification complete: 153 tests pass against genuine HA 2026.9.2; full Ruff lint and formatting pass. Exact repeated cloud records are normalized without hiding conflicting metadata. A masked refresh-token field supports private account enrollment; transient account verification can reuse a rotated token in flow memory. Confirmation is bounded by 61 reads, 3-second intervals and a 180-second deadline, tolerating temporary offline reports only after acknowledgement. Commands are never replayed.
G5 live setup verified: account enrollment succeeded through the masked renewable-token field and the entry reports loaded. Both NARAH units have fan, reported-mode/speed, filter and connectivity entities and correct room assignments. Home Assistant Studio Medium-to-Low control completed without any command replay. Low reporting exceeded 90 seconds, so final confirmation now allows 180 seconds and 61 reads; virtual-clock regression covers a late response after 93 seconds. HACS reports installed release v0.1.0 with no pending update. GitHub CI passed for runtime commit a01c4c2. Following the final Home Assistant restart, the account entry is loaded, both fans are online at 25%, and the exact Ventilation dashboard configuration remains saved. Native screenshot beta is disabled; Brave preview navigation times out, and Codex preview reaches HA login. Visual layout verification remains unavailable. Temporary Mac login files were removed after private HA enrollment.
G6 completion review passed: independent runtime and final documentation reviews found no material issues. Public documentation privacy patterns, relative links and whitespace checks pass. LAN research is complete within the available capture access; offline control remains unproven and dashboard visual inspection remains unavailable. These limits are disclosed rather than counted as successful verification.

### Task 5: LAN control research (after current setup is complete)

- [x] Research local control using the existing Espressif Wi-Fi boards, with no additional hardware.
- [x] Inspect manufacturer documentation, public app source and bounded local TCP/HTTP behavior; packet capture remains unavailable with current access.
- [x] Distinguish the verified registration page and cloud commands from unproven LAN/offline control.
- [x] Report the MQTT/TLS hypothesis, evidence, limitations and a passive capture plan in docs/lan-control.md. No firmware or network changes performed.
