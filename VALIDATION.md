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
