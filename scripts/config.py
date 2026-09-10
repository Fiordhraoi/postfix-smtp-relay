"""Strict, side-effect-free environment validation and Postfix rendering."""
import ipaddress
import re
from pathlib import Path


def boolean(env, key, default='false'):
    value = env.get(key, default)
    if value not in ('true', 'false'):
        raise ValueError(f'{key} must be true or false')
    return value == 'true'


def hostname(value, key):
    if len(value) > 253 or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', value):
        raise ValueError(f'{key} must be a DNS hostname')
    if any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', x) for x in value.split('.')):
        raise ValueError(f'{key} has an invalid DNS label')
    return value.lower()


def validate(env):
    c = {}
    for key in ('SMTP_HOSTNAME', 'MAIL_DOMAIN', 'RELAY_HOST'):
        value = env.get(key, '')
        if not value:
            raise ValueError(f'{key} is required')
        if key == 'RELAY_HOST':
            try:
                c[key] = str(ipaddress.ip_address(value))
                continue
            except ValueError:
                pass
        c[key] = hostname(value, key)
    for key, default, maximum in [('RELAY_PORT', '587', 65535), ('MESSAGE_SIZE_LIMIT', '52428800', 2147483647)]:
        value = env.get(key, default)
        if not re.fullmatch(r'[0-9]+', value) or not 1 <= int(value) <= maximum:
            raise ValueError(f'{key} must be an integer between 1 and {maximum}')
        c[key] = str(int(value))
    networks = env.get('TRUSTED_NETWORKS', '')
    allow_empty = boolean(env, 'ALLOW_EMPTY_TRUSTED_NETWORKS')
    if not networks.strip() and not allow_empty:
        raise ValueError('TRUSTED_NETWORKS is empty; explicitly set ALLOW_EMPTY_TRUSTED_NETWORKS=true')
    c['networks'] = ['127.0.0.0/8', '[::1]/128']
    for item in networks.split(',') if networks.strip() else []:
        try:
            if '/' not in item:
                raise ValueError()
            network = ipaddress.ip_network(item.strip(), strict=True)
        except ValueError:
            raise ValueError('TRUSTED_NETWORKS must contain canonical IPv4/IPv6 CIDRs') from None
        if network.prefixlen == 0:
            raise ValueError('TRUSTED_NETWORKS must not contain a default route')
        c['networks'].append(f'[{network.network_address}]/{network.prefixlen}' if network.version == 6 else str(network))
    c['auth'] = boolean(env, 'SMTP_AUTH_ENABLED')
    c['username'] = env.get('SMTP_AUTH_USERNAME', '')
    c['password'] = env.get('SMTP_AUTH_PASSWORD', '')
    secret = env.get('SMTP_AUTH_PASSWORD_FILE', '')
    if secret:
        try:
            c['password'] = Path(secret).read_text(encoding='utf-8').removesuffix('\n').removesuffix('\r')
        except (OSError, UnicodeError):
            raise ValueError('SMTP_AUTH_PASSWORD_FILE must be a readable UTF-8 file') from None
    if c['auth']:
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', c['username']):
            raise ValueError('SMTP_AUTH_USERNAME must use 1-64 letters, digits, underscore, dot or hyphen')
        if not c['password'] or any(x in c['password'] for x in ('\n', '\r', '\x00')):
            raise ValueError('SMTP AUTH requires a nonempty single-line password')
    c['relay_auth'] = boolean(env, 'RELAY_AUTH_ENABLED', 'true')
    c['relay_username'] = env.get('RELAY_AUTH_USERNAME', '')
    c['relay_password'] = env.get('RELAY_AUTH_PASSWORD', '')
    relay_secret = env.get('RELAY_AUTH_PASSWORD_FILE', '')
    if relay_secret:
        try:
            c['relay_password'] = Path(relay_secret).read_text(encoding='utf-8').removesuffix('\n').removesuffix('\r')
        except (OSError, UnicodeError):
            raise ValueError('RELAY_AUTH_PASSWORD_FILE must be a readable UTF-8 file') from None
    if c['relay_auth']:
        if not c['relay_username'] or any(x.isspace() or x == ':' or ord(x) < 32 or ord(x) == 127 for x in c['relay_username']):
            raise ValueError('RELAY_AUTH_USERNAME is required and must not contain whitespace, colons or control characters')
        password = c['relay_password']
        if not password or password != password.rstrip() or any(ord(x) < 32 or ord(x) == 127 for x in password):
            raise ValueError('RELAY_AUTH_PASSWORD requires a nonempty single-line password without trailing whitespace or control characters')
    c['tls_level'] = env.get('OUTBOUND_TLS_LEVEL', 'secure')
    if c['tls_level'] not in ('none', 'may', 'encrypt', 'verify', 'secure'):
        raise ValueError('OUTBOUND_TLS_LEVEL must be none, may, encrypt, verify or secure')
    if c['relay_auth'] and c['tls_level'] not in ('encrypt', 'verify', 'secure'):
        raise ValueError('Upstream AUTH requires OUTBOUND_TLS_LEVEL=secure, verify or encrypt; plaintext fallback is prohibited')
    c['ca_file'] = env.get('OUTBOUND_TLS_CA_FILE', '') or '/etc/ssl/certs/ca-certificates.crt'
    if env.get('OUTBOUND_TLS_CA_FILE') and (not re.fullmatch(r'/[A-Za-z0-9_./-]+', c['ca_file']) or not Path(c['ca_file']).is_file()):
        raise ValueError('OUTBOUND_TLS_CA_FILE must be an existing absolute certificate file')
    c['cert'] = env.get('TLS_CERT_FILE', '')
    c['key'] = env.get('TLS_KEY_FILE', '')
    if bool(c['cert']) != bool(c['key']):
        raise ValueError('TLS_CERT_FILE and TLS_KEY_FILE must be supplied together')
    for field in ('cert', 'key'):
        value = c[field]
        if value and (not re.fullmatch(r'/[A-Za-z0-9_./-]+', value) or not Path(value).is_file()):
            raise ValueError('TLS paths must be existing absolute files without whitespace or special characters')
    return c


def relay_destination(c):
    relay = c['RELAY_HOST']
    if ':' in relay:
        relay = 'IPv6:' + relay
    return f'[{relay}]:{c["RELAY_PORT"]}'


def render(c):
    settings = {
        'compatibility_level': '3.6', 'inet_interfaces': 'all', 'inet_protocols': 'all',
        'myhostname': c['SMTP_HOSTNAME'], 'mydomain': c['MAIL_DOMAIN'], 'myorigin': '$mydomain',
        'mydestination': '', 'relay_domains': '', 'local_transport': 'error:local delivery disabled',
        'mynetworks': ', '.join(c['networks']), 'relayhost': relay_destination(c),
        'smtpd_relay_restrictions': 'permit_mynetworks, permit_sasl_authenticated, reject_unauth_destination',
        'smtpd_recipient_restrictions': 'reject_non_fqdn_recipient',
        'smtpd_sasl_auth_enable': 'yes' if c['auth'] else 'no', 'smtpd_sasl_type': 'cyrus',
        'smtpd_sasl_path': 'smtpd', 'smtpd_sasl_local_domain': '$myhostname',
        'smtpd_sasl_security_options': 'noanonymous', 'smtpd_tls_auth_only': 'yes',
        'smtpd_tls_security_level': 'may', 'smtpd_tls_cert_file': c['cert'], 'smtpd_tls_key_file': c['key'],
        'smtpd_tls_protocols': '>=TLSv1.2', 'smtpd_tls_mandatory_protocols': '>=TLSv1.2',
        'smtp_sasl_auth_enable': 'yes' if c['relay_auth'] else 'no',
        'smtp_sasl_password_maps': 'hash:/etc/postfix/relay_passwd' if c['relay_auth'] else '',
        'smtp_sasl_security_options': 'noanonymous, noplaintext',
        'smtp_sasl_tls_security_options': 'noanonymous',
        'smtp_sasl_mechanism_filter': 'plain, login',
        'smtp_tls_security_level': c['tls_level'],
        'smtp_tls_CAfile': c['ca_file'], 'smtp_tls_protocols': '>=TLSv1.2',
        'smtp_tls_mandatory_protocols': '>=TLSv1.2', 'message_size_limit': c['MESSAGE_SIZE_LIMIT'],
        'maillog_file': '/dev/stdout', 'smtpd_banner': '$myhostname ESMTP',
        'disable_vrfy_command': 'yes', 'smtpd_helo_required': 'yes', 'biff': 'no',
        'append_dot_mydomain': 'no', 'readme_directory': 'no',
    }
    return ''.join(f'{key} = {value}\n' for key, value in settings.items())
