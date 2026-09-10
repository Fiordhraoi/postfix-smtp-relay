# Barebones setup: your first SMTP relay

This guide takes you from a **fresh Ubuntu Server 24.04 machine** to a running
relay for a copier or application. Run commands in the Ubuntu terminal, one
block at a time. You need a user with `sudo` access. When sudo requests your
password, nothing appears as you type; press Enter when finished.

Use a dedicated Linux server or VM for deployment. Windows/WSL with Docker
Desktop is useful for testing, but does not establish production source-IP
behavior. These installation steps are for Ubuntu Server, not PowerShell.

## 1. Gather these details first

Ask your network/mail administrator for:

| Detail | Example only | Used for |
| --- | --- | --- |
| Static LAN IP for this server | `10.10.1.10` | Devices connect here |
| DNS name pointing to that IP | `smtp01.example.local` | Relay identity |
| Your email domain | `example.com` | Sender domain |
| IP of a permitted copier/application | `10.10.1.50` | Anonymous relay permission |
| Upstream mail server | `smtp.example.com` | Where mail goes next |
| Upstream port | `587` | STARTTLS connection to the upstream |
| Upstream username | `relay@example.com` | Login supplied by your mail provider |
| Upstream password | Your provider's SMTP password | Authentication to the upstream |
| A test sender and recipient | Addresses you control | Delivery test |

**Replace all example values with your real settings.** Configuring a hostname
here does not create a DNS record or give the server a static IP.

This guide assumes an upstream that accepts username/password authentication
on port 587 with STARTTLS and a trusted certificate. Ask your provider for the
correct SMTP hostname and login; OAuth-only services are not supported.
An IP-trusted server without a login is also supported; see the alternative in
step 4 and [M365 connector prerequisites](../README.md#microsoft-365-connector-prerequisites).

## 2. Install Docker on the Ubuntu server

Docker runs the relay in a container. Compose reads the supplied deployment file.
If Docker already works, skip installation and run the verification commands.

These commands assume a fresh server. If you already installed Docker through
another source, follow [Docker's official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/)
to resolve conflicting packages first.

Install the download tools and Docker's package-signing key:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git nano
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Add Docker's package repository. Paste the **whole block**, including the final
`EOF` line. The temporary `>` prompts while entering this block are normal.

```bash
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

Install and start Docker:

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

Look for **Hello from Docker!** and a Compose version of **2.30.0 or newer**
(version 5.x is also suitable). This guide uses `sudo docker` throughout so
you do not need to change user-group permissions.

## 3. Download the deployment files and pull the ready-made image

The ready-made image is hosted in GitHub Container Registry (GHCR). You do not
need to build it or install Postfix yourself. It currently supports **Linux amd64**
(standard Intel/AMD 64-bit servers).

Download the small repository containing the deployment files:

```bash
cd ~
git clone https://github.com/Fiordhraoi/postfix-smtp-relay.git smtp-relay
cd smtp-relay
cp .env.example .env
chmod 600 .env
```

Pull the image:

```bash
sudo docker compose pull
```

Compose downloads `ghcr.io/fiordhraoi/postfix-smtp-relay:latest`. The equivalent
standalone command is:

```bash
sudo docker pull ghcr.io/fiordhraoi/postfix-smtp-relay:latest
```

You only need one of those pull commands. No GitHub login is needed once the
package is public. If the pull reports `denied` or `unauthorized`, check the
[package visibility instructions](PUBLISHING.md#make-the-package-public-once).

Run all remaining Compose commands from this `smtp-relay` directory.

## 4. Enter your site settings

Open the configuration file:

```bash
nano .env
```

Change these existing lines. Do not add duplicate lines. Example:

```dotenv
SMTP_HOSTNAME=smtp01.example.local
MAIL_DOMAIN=example.com
TRUSTED_NETWORKS=10.10.1.50/32
RELAY_HOST=smtp.example.com
RELAY_PORT=587
RELAY_AUTH_ENABLED=true
RELAY_AUTH_USERNAME=relay@example.com
RELAY_AUTH_PASSWORD=replace-with-your-upstream-password
RELAY_AUTH_PASSWORD_FILE=
```

What each setting means:

- **SMTP_HOSTNAME:** the DNS name of this relay server.
- **MAIL_DOMAIN:** your organization's email domain, without an @ sign.
- **TRUSTED_NETWORKS:** which devices may send mail without a password.
  Start with one device: `10.10.1.50/32` means that one IPv4 address.
  Two devices look like `10.10.1.50/32,10.10.1.51/32`.
  A whole subnet such as `10.10.1.0/24` trusts every address in that range;
  use it only if that is intentional.
- **RELAY_HOST:** the upstream mail server, not this relay's own address.
  Enter just the hostname, without `https://`, brackets or a port.
- **RELAY_PORT:** the upstream port; 587 is the default. This uses STARTTLS,
  not implicit TLS on port 465.
- **RELAY_AUTH_USERNAME / RELAY_AUTH_PASSWORD:** the upstream server's login.
  These are separate from any login you choose for your copier or application.
  Leave `RELAY_AUTH_PASSWORD_FILE` blank for this simple method; see the
  [upstream secret-file option](../README.md#upstream-server-and-login) for production.

For the simplest anonymous-device setup, keep these values:

```dotenv
MESSAGE_SIZE_LIMIT=52428800
SMTP_AUTH_ENABLED=false
SMTP_AUTH_USERNAME=smtprelay
SMTP_AUTH_PASSWORD=
SMTP_AUTH_PASSWORD_FILE=
OUTBOUND_TLS_LEVEL=secure
OUTBOUND_TLS_CA_FILE=
TLS_CERT_FILE=
TLS_KEY_FILE=
ALLOW_EMPTY_TRUSTED_NETWORKS=false
```

The size limit is 50 MiB for the entire encoded message, not just the attachment.
`secure` requires encrypted delivery and verifies the upstream's certificate
and hostname. Leave the CA setting blank for a public trusted issuer; private
issuers need the [custom CA setting](../README.md#tls).
Blank inbound certificate settings generate a persistent self-signed
certificate at first startup. It expires after 365 days and needs planned renewal.
Clients that validate certificates will need a trusted certificate instead;
see [certificate setup](../README.md#tls).

Do not put quotes around values or spaces around `=`. Do not commit `.env`
to GitHub. Save in nano with **Ctrl+O**, press **Enter**, then exit with **Ctrl+X**.

**Alternative: upstream without a login.** If your administrator specifies an
IP-trusted server on port 25, replace the upstream host with theirs and change:

```dotenv
RELAY_PORT=25
RELAY_AUTH_ENABLED=false
RELAY_AUTH_USERNAME=
RELAY_AUTH_PASSWORD=
RELAY_AUTH_PASSWORD_FILE=
OUTBOUND_TLS_LEVEL=may
```

`may` permits unencrypted delivery when TLS is unavailable. Keep `secure` when
supported, or use your administrator's required TLS policy. Other STARTTLS ports
can be selected with `RELAY_PORT`; see the [full configuration reference](../README.md#configuration-reference).

## 5. Check that the SMTP ports are free

The supplied configuration uses Linux host networking. Postfix uses the client
IP and your `TRUSTED_NETWORKS` settings to decide who may relay anonymously.

Check whether another program already owns the SMTP ports:

```bash
sudo ss -ltnp '( sport = :25 or sport = :587 )'
```

On the new server there should be no listening entries. If there are, identify
the service and arrange its shutdown before starting this relay.

## 6. Start the relay and check it

```bash
sudo docker compose config --quiet
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=100 smtp-relay
```

The first command produces no output on success. Within roughly a minute,
`compose ps` should show **Up** and **healthy**. If it still says
`health: starting`, wait briefly and check again.

To watch logs as mail arrives:

```bash
sudo docker compose logs -f smtp-relay
```

Press **Ctrl+C** to stop watching; the relay keeps running. It will also restart
automatically when Docker starts after a server reboot.

## 7. Configure the copier or application

Use these settings in the device's email/SMTP page:

| Device setting | Value |
| --- | --- |
| SMTP server | This relay's LAN IP or DNS name, e.g. `10.10.1.10` |
| SMTP port | `25` (or `587`) |
| Authentication | None / Off |
| Username and password | Blank |
| Sender address | A permitted address in your real email domain |
| Encryption | STARTTLS if supported and certificate trust is configured |

Send the device's test email to a mailbox you control, and watch the relay logs.
With authentication disabled, trusted devices can also send without TLS;
the device needs no login. The relay still uses your configured upstream login
when forwarding mail.

Look for the device's real source IP in `connect from` log lines, then a
delivery line containing `status=sent`. That means the upstream accepted the
message; check the recipient's mailbox and spam folder to confirm arrival.
A healthy container alone does not prove upstream delivery works.

## 8. Optional: a device requires a username and password

Keep the device's IP restrictions. In `.env`, change:

```dotenv
SMTP_AUTH_ENABLED=true
SMTP_AUTH_USERNAME=smtprelay
SMTP_AUTH_PASSWORD=replace-with-a-strong-unique-password
```

Keep `SMTP_AUTH_PASSWORD_FILE=` blank for this simple method. Set the same
username/password on the device and **require STARTTLS**. AUTH is not accepted
before TLS, on either port. Install a certificate the device trusts using the
[certificate instructions](../README.md#tls); do not solve trust errors by
disabling certificate checks.

For production, the [secret-file instructions](../README.md#anonymous-and-authenticated-clients)
keep the password out of Docker's environment configuration.

Apply changed settings:

```bash
sudo docker compose up -d --force-recreate
sudo docker compose logs --tail=100 smtp-relay
```

A plain `restart` does not load changes to `.env`.

## 9. Basic troubleshooting and upkeep

| Problem | First check |
| --- | --- |
| Docker socket permission denied | Use `sudo docker` as shown above |
| Cannot connect to Docker | Run `sudo systemctl status docker` |
| Image pull fails | Check Internet/DNS access, package visibility and Linux amd64 support |
| Container exits or keeps restarting | Read logs for a missing/invalid setting or TLS error |
| Address already in use | Check step 5 for another SMTP listener |
| Device cannot connect | Check server address, port and whether the relay is healthy |
| Relay access denied | Compare the logged source IP with `TRUSTED_NETWORKS` |
| AUTH unavailable | Enable AUTH, negotiate STARTTLS, and check certificate trust |
| Mail is deferred | Check upstream hostname, port (normally 587), login and certificate trust |
| Upstream authentication failed | Check `RELAY_AUTH_*` credentials and whether the provider permits SMTP password login |
| No email despite healthy status | Inspect delivery logs and the queue |

See queued mail with:

```bash
sudo docker compose exec smtp-relay postqueue -p
```

After fixing an upstream problem, retry queued deliveries with:

```bash
sudo docker compose exec smtp-relay postqueue -f
```

Keep the same checkout directory and Compose project name. Queued mail and
generated certificates are stored in Docker volumes. **Do not run
`docker compose down -v`**: it deletes those volumes.

Before updates, follow the [backup instructions](../README.md#persistence-backup-and-updates).
Then, from the repository directory:

```bash
git pull --ff-only
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps
```

For more options and diagnostic commands, return to the [full README](../README.md).

The `latest` tag advances after successful tests on the main branch. For a
controlled rollout, follow the [image pinning instructions](PUBLISHING.md#pin-a-deployment)
to deploy a specific tested digest at every site.
