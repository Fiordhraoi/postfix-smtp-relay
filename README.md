# Docker Postfix SMTP relay

A reusable SMTP relay for internal devices and applications. Ubuntu 24.04,
Postfix and Cyrus SASL provide ports 25 and 587, optional LOGIN/PLAIN client
authentication, inbound STARTTLS, and forwarding to one upstream SMTP server.
There are no mailboxes, IMAP services, web interfaces or outbound credentials.
Licensed under GNU AGPL version 3 only (`AGPL-3.0-only`).

**New to Docker? Start with the [barebones setup guide](docs/BAREBONES-SETUP.md)** for installation, pulling the image, configuration and your first test email.

## License

Copyright (c) 2026 SMTP Relay Contributors.

This project's original code, configuration and documentation are licensed under
the GNU Affero General Public License, version 3 only. See [LICENSE](LICENSE)
for the complete terms. The software is provided without warranty.

Distributed covered derivatives must retain AGPL licensing and provide the
corresponding source as required by the license. If you modify the program and
users interact with the modified version over a network, section 13 requires a
prominent offer of its corresponding source to those users at no charge.
Source availability is owed to the relevant recipients/users; the license does
not require every private modification to be published to the entire world.

Postfix, Ubuntu and other separately packaged dependencies retain their own
licenses. Merely using this relay to send email does not relicense client
applications or email contents. Versions previously published under MIT remain
available under those terms; this change does not revoke earlier grants.

## Validation status

GitHub Actions has successfully built the image and passed the unit tests,
Compose validation and live SMTP integration suite on Ubuntu 24.04.
See the [successful validation run](https://github.com/Fiordhraoi/postfix-smtp-relay/actions/runs/34406643929)
and [validation record](VALIDATION.md). Perform the site acceptance checks below
before production rollout, including real client IPs, firewall rules, certificate
trust and your Microsoft 365 connector.

## Quick start

Use a dedicated Linux host (Ubuntu 24.04 recommended), rootful Docker Engine
and Docker Compose **2.30.0 or newer** (needed for raw environment files).
Ensure ports 25 and 587 are free; stop the old host Postfix service before deploying.
Set firewall rules before starting the container.

```sh
git clone https://github.com/Fiordhraoi/postfix-smtp-relay.git smtp-relay
cd smtp-relay
cp .env.example .env
chmod 600 .env
# Edit .env: hostname, domain, trusted client CIDRs and upstream host.
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f smtp-relay
```

Compose pulls the ready-made Linux amd64 image from
`ghcr.io/fiordhraoi/postfix-smtp-relay:latest`. No local build is needed.
The example settings are placeholders, not a working M365 tenant. Values in `.env` are literal: **do not quote them**.
Compose raw format preserves dollar signs, hashes, spaces and backslashes in
passwords. Prefer a secret file for production. Never commit `.env`.

## Architecture and security model

Clients → Postfix smtpd on 25/587 → persistent queue → configured upstream.
Cyrus SASL reads a startup-generated local password database; no SASL daemon or
Dovecot is required. The root startup process validates settings and TLS, builds
the database, repairs queue permissions and runs `postfix check`. It then
supervises `postfix start-fg`, handles TERM/INT with `postfix stop`, and waits for
shutdown. Postfix logs through postlogd to stdout. A 60-second Compose stop grace
period allows orderly shutdown; queued messages remain on disk even after a kill.

Both listeners apply `permit_mynetworks, permit_sasl_authenticated,
reject_unauth_destination`. Trusted clients may relay without authentication or
TLS. Untrusted clients must authenticate over TLS. AUTH is unavailable before
STARTTLS on both ports; only LOGIN and PLAIN are configured. Submission deliberately
allows trusted anonymous clients and does not require TLS for all traffic.
Neither local domains nor relay destination domains are accepted anonymously
from untrusted clients. Authentication grants relay access to any recipient.

Loopback is trusted, including processes on the Linux host and other host-network
containers. Treat host access as privileged. Choose narrow trusted networks;
any compromised trusted device can send mail. Empty trust lists require an explicit
opt-in, while IPv4/IPv6 default routes are rejected outright. The validator cannot
decide whether a valid CIDR is appropriate for your site.

The container needs root for Postfix master, low ports, ownership changes and
privilege dropping. Worker services use Postfix's packaged users. Compose drops
all capabilities and restores CHOWN, DAC_OVERRIDE, FOWNER, FSETID, SETGID, SETUID,
NET_BIND_SERVICE and KILL. It does not use privileged mode, a Docker socket,
NET_ADMIN, or extra exposed services. Services are unchrooted to access DNS,
SASL and mounted certificates; the container provides filesystem isolation.

## Configuration reference

All variables are read at startup. Recreate the container after changes with
`docker compose up -d --force-recreate`; `docker compose restart` does not reload
changed environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SMTP_HOSTNAME` | required | Relay DNS hostname and SASL realm |
| `MAIL_DOMAIN` | required | Domain for locally originated mail, not a mailbox domain |
| `TRUSTED_NETWORKS` | required | Comma-separated canonical IPv4/IPv6 CIDRs; no implicit bridge trust |
| `RELAY_HOST` | required | Bare DNS name or IP, without brackets or port |
| `RELAY_PORT` | `25` | Upstream port, 1–65535 |
| `MESSAGE_SIZE_LIMIT` | `52428800` | Maximum message bytes, 1–2147483647; MIME encoding counts |
| `SMTP_AUTH_ENABLED` | `false` | Enable local client SMTP AUTH |
| `SMTP_AUTH_USERNAME` | empty | Required when AUTH enabled; 1–64 letters, digits, `_`, `.`, `-` |
| `SMTP_AUTH_PASSWORD` | empty | Single-line password; environment visible to Docker administrators |
| `SMTP_AUTH_PASSWORD_FILE` | empty | Readable UTF-8 secret file, preferred over environment password |
| `OUTBOUND_TLS_LEVEL` | `may` | `none`, `may`, `encrypt`, `verify`, or `secure` |
| `TLS_CERT_FILE` | empty | Absolute mounted PEM certificate/full-chain path |
| `TLS_KEY_FILE` | empty | Matching unencrypted PEM private key path |
| `ALLOW_EMPTY_TRUSTED_NETWORKS` | `false` | Permit no additional trusted CIDRs; loopback remains trusted |

Boolean values must be exactly `true` or `false`. CIDRs with host bits set are
rejected; use `10.10.0.0/16`, not `10.10.1.2/16`. IPv6 example:
`TRUSTED_NETWORKS=10.10.0.0/16,2001:db8:1234::/48`. Paths must be absolute and
contain only letters, digits, underscores, dots, slashes and hyphens. Secret
files may contain one final LF or CRLF, which is removed; spaces are preserved.
A specified missing secret fails startup even if AUTH is disabled.

Outbound SASL is always disabled. Future upstream authentication can be added
separately via `smtp_sasl_*` and a dedicated secret map without changing inbound
`smtpd_sasl_*`. It is intentionally not implemented here.

## Anonymous and authenticated clients

For anonymous devices, leave AUTH disabled and include their actual source
addresses in `TRUSTED_NETWORKS`. Configure the device with this relay's address
and port 25 or 587. Enable STARTTLS on devices that support it.

For authenticated devices, set `SMTP_AUTH_ENABLED=true`, choose a username and
supply a strong unique password. Clients should use that username (or
`username@SMTP_HOSTNAME`) and STARTTLS. Devices that cannot negotiate TLS 1.2 or
newer must use trusted anonymous relay; plaintext AUTH is not supported.

To use Compose secrets, create `secrets/smtp_auth_password` using a secure editor,
restrict its permissions, and add a `compose.override.yaml`:

```yaml
services:
  smtp-relay:
    secrets:
      - smtp_auth_password
secrets:
  smtp_auth_password:
    file: ./secrets/smtp_auth_password
```

Set `SMTP_AUTH_PASSWORD_FILE=/run/secrets/smtp_auth_password` in `.env` and clear
`SMTP_AUTH_PASSWORD`. Compose secrets are mounted files, not an encrypted secret
store. The database is recreated on each launch so removed credentials cannot
remain valid. Rotation requires container recreation.

## TLS

If neither certificate variable is set, startup creates a 3072-bit RSA self-signed
certificate valid for 365 days in the persistent `tls` volume. It is reused,
not regenerated, across restarts. Expired, incomplete or mismatched material
fails startup. Changing the hostname does not rotate an existing certificate;
replace it deliberately. Monitor expiration and plan renewal.

For production, mount a trusted certificate and private key read-only:

```yaml
services:
  smtp-relay:
    volumes:
      - ./certs:/certs:ro
```

Set `TLS_CERT_FILE=/certs/smtp.crt` and `TLS_KEY_FILE=/certs/smtp.key`. Restrict the
host private key to root. Supply the leaf certificate followed by intermediate
certificates. Restart after renewal so Postfix reads the new files. Clients must
trust the issuer and connect using a matching certificate hostname.

Outbound `may` offers opportunistic encryption and permits plaintext fallback.
`encrypt` requires TLS but does not authenticate the server certificate; `verify`
and `secure` also apply Postfix certificate verification/name policies. Use
`secure` with a valid upstream DNS name and trusted certificate when appropriate.
`none` disables outbound TLS. Neither a mounted inbound certificate nor local
AUTH configures certificate-based M365 connector authentication.

## Docker networking and firewall

The recommended deployment uses **native Linux host networking**. It shares
the host network namespace, avoids Docker port publishing, NAT and userland
proxies, and lets Postfix see the source IP arriving at the host. Upstream
routers or firewalls may still SNAT traffic: verify the resulting address in
Postfix's `connect from` log lines before trusting a subnet.

Normal native Linux bridge published-port traffic using DNAT can preserve a
remote IPv4 source, but this is not a guarantee for every path. Hairpin/local
traffic, userland proxies, IPv6-to-IPv4 publishing, rootless engines, Docker
Desktop virtualization and Swarm ingress can alter it. Bridge mode is acceptable
only after testing every relevant path with trusted and untrusted clients.
Never compensate by trusting `172.17.0.0/16` or any entire bridge subnet.
Docker Desktop's host networking is not equivalent to native Linux namespace
sharing and is not this project's recommended production platform.

Allow inbound TCP 25/587 only from intended device networks, VPNs or explicitly
approved authenticated clients. Apply equivalent IPv6 firewall rules. No public
Internet listener is required. Allow outbound DNS resolution and TCP to the
upstream relay port. Restrict other devices from directly reaching external SMTP
if that is part of your mail policy. Host mode uses the host INPUT firewall path;
bridge-published ports require Docker-aware forwarding rules and may bypass
ordinary UFW expectations. Network ACLs complement, rather than replace, Postfix
relay restrictions. Do not expose the Docker API.

Sources: [Docker host networking](https://docs.docker.com/engine/network/drivers/host/),
[Docker port publishing](https://docs.docker.com/engine/network/port-publishing/),
[Postfix logging](https://www.postfix.org/MAILLOG_README.html),
[Postfix parameters](https://www.postfix.org/postconf.5.html).

## Microsoft 365 connector prerequisites

Use your tenant's MX endpoint, such as
`example-com.mail.protection.outlook.com`, on TCP 25. Configure an Exchange Online
inbound connector from your organization's email server that trusts your site's
dedicated static public NAT IP. No upstream username/password is used. Confirm
the actual public egress IP, accepted sender domain, tenant MX target, connector
scope and any TLS requirement with your M365 administrator. Allow TCP 25 through
the ISP/firewall; some hosting providers block it. Configure SPF for authorized
senders and review tenant anti-spam and sending limits. This does not bypass
Microsoft restrictions on third-party hosted relay scenarios.

See [Microsoft's device and application SMTP setup guidance](https://learn.microsoft.com/en-us/exchange/mail-flow-best-practices/how-to-set-up-a-multifunction-device-or-application-to-send-email-using-microsoft-365-or-office-365).
The connector's public IP trust is independent from this relay's internal CIDRs.
Use `OUTBOUND_TLS_LEVEL=encrypt` or stronger when your connector requires TLS.

## Automated tests and site acceptance

```sh
python3 -m unittest discover -s tests -v
python3 tests/integration.py
```

The integration runner builds the image, starts an isolated internal Docker
network with a mock upstream, and probes both ports from a separate client. It
checks trusted anonymous acceptance, untrusted rejection, AUTH hidden before TLS,
LOGIN and PLAIN after TLS, wrong-password rejection, AUTH disabled, advertised
message size, delivery to the mock, `postfix check`, `postconf -n`, health and
queue persistence across container recreation. It uses the same capability
restrictions as Compose and cleans up only its uniquely named resources.
Image package downloads require Internet access; SMTP tests never contact M365.

Before site rollout, test from a real allowed and disallowed device/VLAN and
inspect source-IP logs. Check IPv6 separately if enabled. Verify real certificate
trust, secret mounting, NAT public IP, firewall restrictions and connector
delivery. The Docker test topology does not establish your production network's
source-address behavior. Monitor disk space, queue age and delivery failures;
health only checks the local process, both listeners and STARTTLS advertisement.

## Manual SMTP tests

From a trusted device, connect with `nc smtp01.example.local 25` and type:

```text
EHLO testhost.example.local
MAIL FROM:<test@example.com>
RCPT TO:<recipient@example.net>
DATA
Subject: SMTP Relay Test
From: test@example.com
To: recipient@example.net

This is an SMTP relay test.
.
QUIT
```

Use a recipient you control: DATA submits real mail. Repeat RCPT from an
untrusted network; expect `554 Relay access denied` before DATA. Test port 587 too.

```sh
openssl s_client -starttls smtp -connect smtp01.example.local:587 -servername smtp01.example.local -crlf
swaks --server smtp01.example.local --port 25 --from test@example.com --to recipient@example.net
swaks --server smtp01.example.local --port 587 --tls --auth LOGIN --auth-user smtprelay --from test@example.com --to recipient@example.net --auth-password
```

Let swaks prompt for the password rather than putting it in shell history. Use
`--tls-verify` for certificate verification with swaks and the appropriate CA
options with OpenSSL; an encrypted connection alone does not prove identity.

## Operations and troubleshooting

```sh
docker compose logs -f smtp-relay
docker compose exec smtp-relay postconf -n
docker compose exec smtp-relay postfix check
docker compose exec smtp-relay postqueue -p
docker compose exec smtp-relay postqueue -j
docker compose exec smtp-relay postqueue -f
docker compose exec smtp-relay postcat -q QUEUE_ID
```

`postqueue -f` retries delivery; avoid repeatedly flushing during outages.
`postcat` exposes message contents, so treat output as confidential. Deleting
queued messages with `postsuper -d` is irreversible; use it only deliberately.

Connection refused: check port conflicts, container health and firewall rules.
Relay denied: compare actual logged client IP against the configured CIDRs; do
not broaden trust to mask NAT. AUTH missing: first negotiate STARTTLS, then EHLO.
AUTH failure: check username/realm, secret contents and recreate after rotation.
TLS failure: check expiry, key pairing, chain, hostname and device TLS support.
Message too large: account for MIME/base64 expansion and the upstream's own limit.
Deferred mail: inspect the queue's remote SMTP response and DNS/TCP reachability.

M365 `550 5.7.64 TenantAttribution; Relay Access Denied` commonly points to
connector attribution: verify endpoint, public IP and connector configuration.
Other `5.7.x` relay/sender errors require checking accepted domains and policies;
use the complete enhanced response rather than just the numeric code. `4.x.x`
throttling/temporary failures remain queued; `5.x.x` permanent failures normally
produce a bounce. Connection timeouts often indicate blocked TCP 25. This relay
does not guarantee delivery or monitor the upstream as part of its health check.

## Persistence, backup and updates

Compose retains `queue` at `/var/spool/postfix` and `tls` at `/var/lib/postfix-tls`.
Keep the same Compose project name/directory across upgrades, or use `docker
compose -p smtp-relay` consistently from the first deployment. A different
project name creates different volumes. Never run `docker compose down -v` when
you need queued mail or generated keys. Never share one queue between replicas.

For a consistent backup, stop the relay first, then snapshot or archive both
named volumes preserving numeric ownership and permissions. For example, find
the actual names with `docker volume ls`, substitute them below, and run from
the repository (pull the image first):

```sh
docker compose stop
mkdir -p backup
chmod 700 backup
docker run --rm --entrypoint tar -v ACTUAL_QUEUE_VOLUME:/source:ro -v "$PWD/backup:/backup" ghcr.io/fiordhraoi/postfix-smtp-relay:latest -C /source -cpf /backup/queue.tar .
docker run --rm --entrypoint tar -v ACTUAL_TLS_VOLUME:/source:ro -v "$PWD/backup:/backup" ghcr.io/fiordhraoi/postfix-smtp-relay:latest -C /source -cpf /backup/tls.tar .
docker compose start
```

Encrypt backups; they contain mail and private keys. Back up `.env`, secret files
and administrator certificates separately. Restore into empty stopped volumes
using `tar --numeric-owner -xpf`, with a compatible Postfix version, before
starting. Test restoration off-network to avoid duplicate deliveries. Do not
restore an old queue over a running or nonempty queue.

To update after reviewing changes and taking a backup:

```sh
git pull --ff-only
docker compose pull
docker compose up -d
docker compose logs --tail=100 smtp-relay
```

The [Test and publish workflow](.github/workflows/test.yml) builds a Linux amd64
image, runs the integration suite against that exact image, and publishes it to
GHCR only after all tests pass on main. Pull requests run tests without publishing.
Tags include `latest` and `sha-<full-commit-sha>`. Rebuilding a commit may pick up
new Ubuntu packages; use a digest for an immutable deployment.

See [publishing, package visibility and image pinning](docs/PUBLISHING.md).
For local development, use the source-build override:

```sh
docker compose -f compose.yaml -f compose.build.yaml build --pull
docker compose -f compose.yaml -f compose.build.yaml up -d
```

The default deployment continues using GHCR unless that override is explicitly
selected. Retain the previous image for rollback and check queue compatibility
before downgrading. The source revision is recorded in the image's
`org.opencontainers.image.revision` label; source is available from this
repository at that revision. Project license text is included in the image.
