# Validation record

On 2026-09-09, [GitHub Actions run #4](https://github.com/Fiordhraoi/postfix-smtp-relay/actions/runs/34406643929)
passed for implementation commit `46013c9d5e91bfa9f36f021095b35b79fcedbd3e`
on an Ubuntu 24.04 GitHub-hosted runner.

Verified:

- Seven configuration unit tests, including invalid-input subcases.
- Docker Compose configuration validation.
- Docker image build with Ubuntu 24.04 and Postfix 3.8.6.
- Actual generated configuration via `postconf -n` and `postfix check`.
- Health check and SMTP acceptance on ports 25 and 587.
- Trusted anonymous relay acceptance and untrusted anonymous rejection.
- AUTH unavailable before STARTTLS; LOGIN and PLAIN work after TLS.
- Invalid-password rejection and AUTH-disabled behavior.
- Message-size advertisement and delivery to an isolated mock upstream.
- Queue preservation across container recreation while upstream is unavailable.
- Restricted capability configuration shared with Compose.

Initial live runs exposed missing packaged manpages and proxy-map services;
these were fixed before the successful run. FSETID preserves Postfix's packaged
setgid helper permissions during startup permission repair.

Remaining site-specific checks: actual IPv4/IPv6 source-address preservation,
firewall policy, administrator certificate trust/renewal, mounted production
secrets, NAT public IP and real Microsoft 365 connector delivery. The automated
suite does not send mail to Microsoft 365 or certify your site's network.

## Local WSL 2 / Docker Desktop validation — 2026-09-10

Tested repository commit: `55bc411f3ca0a3cfa991e70d4ac150401406d55d`.

Environment: Ubuntu 24.04 under WSL 2, Docker Desktop 4.90.0,
Docker Engine 29.7.2 (Linux amd64), Docker Compose v5.5.1.
The image installed Postfix 3.8.6-1ubuntu0.1 from Ubuntu packages.

Commands executed successfully:

```sh
python3 -m unittest discover -s tests -v
cp .env.example .env
docker compose config --quiet
python3 -u tests/integration.py
```

Results:

- All seven unit tests passed.
- Compose configuration validation passed.
- Docker image built successfully.
- Real `postconf -n` output was inspected and `postfix check` passed.
- Trusted anonymous SMTP and authenticated SMTP worked on both 25 and 587.
- Untrusted anonymous relay and incorrect passwords were rejected.
- AUTH was unavailable before STARTTLS; LOGIN and PLAIN worked after TLS.
- AUTH-disabled mode and advertised message size passed.
- Messages reached the isolated mock upstream.
- Queued messages survived container recreation while the upstream was stopped.
- The suite exited with code 0 and reported:
  `Integration passed: ports, relay ACLs, TLS/AUTH, delivery, queue persistence`.
- Follow-up Docker queries confirmed removal of this run's containers,
  queue volume and internal network.

No implementation changes were needed. Tests used an internal Docker network
without publishing SMTP ports or contacting Microsoft 365. These results verify
local container behavior; they do not replace the site-specific production
network, mounted-certificate/secret and Microsoft 365 checks listed above.

## First GHCR image publication — 2026-09-10

[GitHub Actions run](https://github.com/Fiordhraoi/postfix-smtp-relay/actions/runs/34501706838)
passed unit tests, Compose validation and integration tests, then published the
exact tested image for source revision
`af48e3f7d2ff3528f37c52133d81bb4851b15096`.

Published tags:

- `ghcr.io/fiordhraoi/postfix-smtp-relay:latest`
- `ghcr.io/fiordhraoi/postfix-smtp-relay:sha-af48e3f7d2ff3528f37c52133d81bb4851b15096`

Verified image digest:
`sha256:7c8a6ebc208da30e3008a65ec0d16c42d6f237b7831d1f3ecfaae62f6b4dc349`.

An anonymous Docker pull from GHCR succeeded locally. No package visibility
change was needed. Image labels correctly identified the source revision and
AGPL-3.0-only license. The full integration suite then passed again against the
downloaded image selected by digest, including SMTP/TLS/AUTH, relay restrictions,
mock delivery and queue persistence.

The GHCR-based Compose file and optional source-build override were validated
locally. Current published platform: Linux amd64. This does not replace the
site-specific checks above.
