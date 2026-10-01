# Changelog

User-facing changes, fixes and implementation findings are recorded here. Add changes under **Unreleased** before publishing; move them into a versioned section when that version is released. Documentation changes do not change the installed integration version.

## [Unreleased]

### Documentation and findings

- Defined the next [LAN protocol-discovery steps](docs/lan-control.md): a manufacturer request for stock Wi-Fi control/authentication and a proposed native-app audit, with status readback and physical/offline verification gates. Clarified that further TLS captures alone do not supply plaintext commands. Rechecked the Modbus tables and recorded unresolved active mode/speed write, unit-address and serial-framing details before any wired implementation. No native-app audit, local commands, broker redirection or hardware changes were performed.
- Obtained private passive packet summaries through the existing UniFi AP Debug consoles. Board-filtered, bounded `any` captures showed both stock boards exchanging TCP traffic with the same internet endpoint on remote port 8883; a small payload sample had TLS-compatible encrypted-record framing. Recorded the bridge-only visibility limitation, duplicate observations and the absence of decoded MQTT or verified local commands. Raw captures and household identifiers are excluded from Git; no investigator fan commands or network changes were made. See the [LAN investigation](docs/lan-control.md).
- Verified the actual 08:00 Europe/Lisbon time triggers on 1 October: each schedule issued one 25% command and finished without trace errors; both units subsequently reported Low/25% in Manual mode with idle automation queues. Physical actuation, the 22:00 clock trigger and live startup behavior remain unverified. Updated the [scheduling guide](docs/scheduling-and-sensors.md).
- Tested common firmware-dependent Espressif interfaces on both stock boards. A fresh nine-port TCP connect/close inventory found only port 80 open; ESPHome API 6053, OTA-numbered TCP 3232/8266 and the optional ESP-AT socket 3333 refused connections. Confirmed an initially inconclusive 3232 result, resolved an unrelated ESPHome mDNS advertisement privately, and recorded the short discovery/UDP limitations. TCP probes sent no application payloads; mDNS queries were read-only discovery. No fan commands, provisioning or firmware changes were sent. UniFi aggregate traffic did not identify broker destinations or command payloads; local fan control remains unproven. See the updated [LAN investigation](docs/lan-control.md).
- Added a [generic scheduling and sensor guide](docs/scheduling-and-sensors.md) for two created, validated and enabled native Home Assistant automations: 100% from 22:00 to 08:00 and 25% otherwise, manual overrides until the next boundary, startup that preserves Off, and queued execution with at most two runs. Only time/startup triggers are used, with a bounded five-minute readiness wait, no reconnect triggers or automatic retries, and no write when the requested speed is already reported. Manually invoked overnight runs completed with both units reporting on at 100% in Manual mode and neither automation still active.
- Documented four explicit dashboard speed actions and separate checks for saved configuration, visual rendering, time-trigger execution, reported state and physical response. Capability-aware Turn off cards disable taps when Stop is unsupported or the fan is not on; 16 synthetic cases passed and the four appended control/status cards were read back without replacing existing cards. Both those cards and the ventilation view were visually verified in the native desktop Home Assistant app, including reported 100%/Manual/Connected and enabled schedules. Phone rendering was not checked. No measured-humidity value or chart was added.
- Schedule validation covered 20 native-evaluator contexts, seven time-edge checks and genuine Home Assistant 2026.9.2 YAML schema validation. The later 08:00 clock-trigger verification is recorded above; the 22:00 trigger and physical fan response remain unverified.
- Recorded the current Stop boundary: inspected units lack TURN_OFF and cloud Stop is hidden. The manufacturer documents standby allowance on SW4; no hidden controls or hardware settings were changed.
- Distinguished the built-in humidity sensor from an exposed measurement. Five cloud dashboards and 25 historical device-detail responses supplied no validated numeric internal RH field; a fresh `/basic` payload remains an evidence gap. Motor PWM and C08/C10 sensitivity settings are not RH readings, and Modbus 30023 refers to the external AIRSENS probe.
- These documentation changes do not change runtime version 0.1.1.

## [0.1.1] — 2026-10-01

### Fixed

- Suppressed underlying exception chains at HTTP/authentication and Home Assistant error boundaries. Safe top-level errors previously could retain provider details or device-route identifiers in a formatted traceback. Synthetic-marker regressions cover the protected paths; errors still report the appropriate failure class and safe message.
- Validation: 166 tests passed, including 13 new privacy regressions demonstrated failing before the fix; full Ruff lint/format, whitespace and independent review passed.

### Documentation and maintenance

- Published the [LAN investigation](docs/lan-control.md): the local HTTP page supplies registration keys; offline fan control remains unproven. Outbound MQTT/TLS is a hypothesis, and the next useful experiment is a private AP/gateway packet capture. No PCAP was obtained with current access.
- Clarified that slow confirmation can reflect cloud delivery or delayed status reporting; the observed delay does not establish when the motor changed speed.
- Recorded successful HACS installation, renewable account enrollment, both device entries, the Studio Medium-to-Low test and restart persistence. Dashboard configuration was read back exactly; visual rendering remains unverified.
- Added repository maintenance rules requiring changelog updates and a privacy review before publication.
- Recorded the [publication privacy audit](docs/privacy-audit.md), including historical Git content, release material, workflow logs and the existing commit-metadata boundary.
- Expanded ignored local capture/log files and added a pinned, checksum-verified Gitleaks workflow that scans full fetched Git history on pushes and pull requests.
- Future commits from the development checkout use the personal GitHub account's noreply identity. Existing published commit metadata is unchanged.

## [0.1.0] — 2026-09-30

### Added

- HACS installation and Add to HACS/Add integration buttons.
- Connectair account discovery, four native fan speeds, reported mode/speed, connectivity and filter countdown sensors for validated NARAH 160 RT/P0024_R000 units.
- Auth0 PKCE sign-in, refresh-token rotation, private Home Assistant storage and reauthentication. An optional masked refresh-token field supports advanced enrollment.
- Per-unit command serialization, coupled-setting preservation and reported-register confirmation. Unsupported models and unavailable controls fail explicitly.
- Diagnostics omit credentials, account/device identifiers, names and raw cloud payloads. Tests use synthetic fixtures.

### Fixed during validation

- Added the official app Origin header required by the cloud API.
- Preserved the latest rotated token in flow memory after transient account-verification failures, avoiding reuse of an already consumed login code/token. Invalid authentication or changed inputs discard that pending state.
- Normalized exact duplicate cloud records while rejecting conflicting or ambiguous controls.
- Extended acknowledged-command confirmation to a three-minute deadline with at most 61 reads. Temporary offline/malformed reports consume further reads; the write is never replayed. Authentication errors fail immediately, and offline units are rejected before a write.
- Hardened private token-storage errors and device availability behavior.

### Findings and limits

- S&P's registered callback can land on an Auth Error page despite returning a usable query callback. The sign-in instructions explain retrieving the preceding callback from browser history. Callback URLs contain private one-time codes.
- A native fan slider includes 0%, so units without an enabled Stop control should use explicit 25/50/75/100% dashboard buttons.
- Boost, automatic-mode selection, unsupported models and local/offline control are not implemented.
- Release validation: 153 tests passed against genuine Home Assistant 2026.9.2; Ruff lint/format and release CI passed. Live enrollment, Home Assistant control and restart persistence were verified separately.

[Unreleased]: https://github.com/rubarksfield/connectair-hacs/compare/v0.1.1...main
[0.1.1]: https://github.com/rubarksfield/connectair-hacs/releases/tag/v0.1.1
[0.1.0]: https://github.com/rubarksfield/connectair-hacs/releases/tag/v0.1.0
