# Repository maintenance

## Change records

- Update `CHANGELOG.md` for every user-facing fix, behavior change or material implementation finding before publishing it.
- Keep unreleased changes under `Unreleased`; create a version section for a release. Do not imply a documentation-only commit changed the installed version.
- Record observed behavior, verification and limitations. Keep inferred MQTT/LAN behavior separate from proven cloud control.

## Publication privacy

- Never commit account passwords, access/refresh tokens, authorization callback URLs/codes, pairing keys, session cookies, private keys, household addresses/IPs/MACs, account/device identifiers, raw cloud dashboards, captures or private Home Assistant configuration.
- Keep temporary credentials and evidence under the ignored `private/` directory, with owner-only permissions. Remove temporary credentials once they are no longer needed.
- Use synthetic fixtures. A public OAuth client ID and vendor API URLs are protocol constants, not user credentials; do not replace them with real account-specific data.
- Before pushing, review staged files and commit metadata, run `git diff --cached --check`, and run `gitleaks git . --log-opts="--all" --redact=100 --ignore-gitleaks-allow` plus `gitleaks git . --staged --redact=100 --ignore-gitleaks-allow` using the pinned workflow version. Check household identifiers manually; a secret scanner does not detect every form of sensitive information.
- Audit reports must not quote possible secret values. Use safe file/line/commit references and counts. Do not publish raw scanner reports or capture files.
- If an actual credential exposure is found, stop publication and report it privately. Do not rewrite published history or rotate shared credentials without the required authorization.
- Use a verified GitHub noreply email for future commits where available. Do not alter global Git identity or rewrite existing commits as a routine privacy fix.

## Verification

- Inspect relevant code and tests first, verify the smallest useful change, and review the final diff.
- Keep TLS certificate verification enabled and credentials in Home Assistant's private config-entry storage.
- Never replay an acknowledged fan command to hide delayed status reporting. Do not claim local/offline control or dashboard visual verification without direct evidence.
