"""Initialize configuration and supervise Postfix, forwarding graceful stops."""
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from config import validate, render, relay_destination


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def prepare():
    c = validate(os.environ)
    if not c['cert']:
        directory = Path('/var/lib/postfix-tls')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        c['cert'], c['key'] = str(directory / 'smtp.crt'), str(directory / 'smtp.key')
        exists = [Path(c[x]).exists() for x in ('cert', 'key')]
        if any(exists) and not all(exists):
            raise ValueError('Persistent TLS material is incomplete; restore the missing file')
        if not any(exists):
            run('openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-days', '365',
                '-subj', f'/CN={c["SMTP_HOSTNAME"]}', '-addext', f'subjectAltName=DNS:{c["SMTP_HOSTNAME"]}',
                '-keyout', c['key'], '-out', c['cert'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.chmod(c['key'], 0o600)
    cert_public = run('openssl', 'x509', '-in', c['cert'], '-pubkey', '-noout', capture_output=True).stdout
    key_public = run('openssl', 'pkey', '-in', c['key'], '-passin', 'pass:', '-pubout', capture_output=True).stdout
    if cert_public != key_public:
        raise ValueError('TLS certificate and key do not match')
    run('openssl', 'x509', '-in', c['cert'], '-checkend', '0', '-noout', stdout=subprocess.DEVNULL)
    Path('/etc/postfix/main.cf').write_text(render(c))
    Path('/etc/postfix/main.cf').chmod(0o644)
    shutil.copyfile('/opt/relay/templates/master.cf', '/etc/postfix/master.cf')
    Path('/etc/postfix/master.cf').chmod(0o644)
    database = Path('/etc/postfix/sasl/sasldb2')
    database.unlink(missing_ok=True)
    Path('/etc/postfix/sasl/smtpd.conf').write_text(
        'pwcheck_method: auxprop\nauxprop_plugin: sasldb\nmech_list: PLAIN LOGIN\nsasldb_path: /etc/postfix/sasl/sasldb2\n')
    Path('/etc/postfix/sasl/smtpd.conf').chmod(0o644)
    if c['auth']:
        run('saslpasswd2', '-p', '-c', '-f', str(database), '-u', c['SMTP_HOSTNAME'], c['username'],
            input=(c['password'] + '\n').encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.chown(database, user='root', group='postfix')
        database.chmod(0o640)
    # The map is readable only by root. Postfix opens it before dropping privileges.
    # Credentials are fed to postmap through stdin, never command-line arguments.
    relay_map = Path('/etc/postfix/relay_passwd.db')
    relay_map.unlink(missing_ok=True)
    if c['relay_auth']:
        run('postmap', '-i', 'hash:/etc/postfix/relay_passwd',
            input=(relay_destination(c) + '\t' + c['relay_username'] + ':' + c['relay_password'] + '\n').encode(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        relay_map.chmod(0o600)
    # Remove secrets from the environment inherited by every Postfix child.
    os.environ.pop('SMTP_AUTH_PASSWORD', None)
    os.environ.pop('RELAY_AUTH_PASSWORD', None)
    c['password'] = ''
    c['relay_password'] = ''
    run('postfix', 'set-permissions')
    run('postfix', 'check')
    run('postconf', '-n')


def main():
    try:
        prepare()
    except ValueError as exc:
        print(f'Configuration error: {exc}', file=sys.stderr)
        return 1
    except (OSError, subprocess.CalledProcessError):
        print('Initialization failed: check file permissions, TLS material and Postfix diagnostics', file=sys.stderr)
        return 1
    child = subprocess.Popen(['postfix', 'start-fg'])
    def stop(signum, frame):
        subprocess.run(['postfix', 'stop'], check=False)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return child.wait()


if __name__ == '__main__':
    sys.exit(main())
