# Publication privacy audit

Reviewed 1 October 2026. This is a record of the inspection, not a guarantee that automated scanning detects every secret.

## Published material inspected

- Full available Git history through `3b768f7`, including all five historical commits, reachable refs and stored blobs.
- Current source, synthetic fixtures, documentation, release `v0.1.0` at `a01c4c2` and its source archive.
- Release text and all six existing GitHub Actions runs: 52 log files containing 3,854 lines.
- Release assets, Actions artifacts, issues, pull requests, comments, repository variables/secrets and other available publication surfaces. There were no uploaded release assets or Actions artifacts, and no issues, pull requests or comments.
- The maintenance changes accompanying this report, reviewed before publication.

## Results and safeguards

Gitleaks **8.30.1**, downloaded from its official release and checked against the published SHA-256 digest, found **zero secrets** in the historical Git scan. Staged changes were checked separately. An isolated synthetic fixture confirmed that both staged and committed GitHub-token patterns are rejected; its values and reports were not published.

Independent source/history and GitHub-surface reviews found no real login credentials, access/refresh tokens, pairing keys, private keys, auth callback codes or household account/device/network identifiers in the audited public material. Files under `private/`, real captures and private Home Assistant configuration were never tracked. Synthetic fixture values and the application's public OAuth client ID are not user credentials.

Runtime credentials remain in Home Assistant's private config-entry storage. Integration diagnostics omit credentials and household identifiers. Raw local evidence and scanner reports remain outside published Git content; scanner reports use redacted output and owner-only local permissions.

The review also found a runtime logging gap: safe top-level errors could retain sensitive provider details or device-route identifiers in their underlying exception chains. Version **0.1.1** suppresses those chains at HTTP/authentication and Home Assistant error boundaries. Thirteen regression checks were demonstrated failing before the fix, then passed; they format the entire traceback and verify that synthetic private markers are absent. The full suite passed 166 tests, with clean Ruff checks and independent review. This is preventive hardening; no actual credential exposure was found in the audited public material.

The new secret-scan workflow uses read-only repository permissions, downloads a pinned checksum-verified scanner and checks full fetched history. It does not inject account credentials, call the live cloud service or upload artifacts. Local publication rules additionally require staged scans and manual checks for household identifiers, which generic secret scanners can miss.

## Commit metadata boundary

The five existing published commits contain the author name/email inherited from the original local Git identity. Those metadata fields are public; they are not login credentials. Their values are not repeated here. Future commits in this checkout use the personal GitHub account's noreply identity. Published history was not rewritten.

## Continuing maintenance

Follow [AGENTS.md](../AGENTS.md), record fixes and findings in [CHANGELOG.md](../CHANGELOG.md), and repeat the privacy checks before publication. Never attach raw callbacks, tokens, HAR/PCAP files or private Home Assistant configuration to public issues.
