"""Run on a Docker Engine host: python3 tests/integration.py (builds image)."""
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
prefix = 'relay-test-' + uuid.uuid4().hex[:8]
containers = []
network = prefix + '-net'
volume = prefix + '-queue'
fixtures = prefix + '-fixtures'
# An explicitly supplied image is tested as-is and never removed by this suite.
supplied_image = os.environ.get('RELAY_TEST_IMAGE')
image = supplied_image or prefix + ':test'


def docker(*args):
    return subprocess.check_output(['docker', *args], cwd=root, text=True).strip()


def launch(name, *args):
    containers.append(name)
    caps = ['--cap-drop=ALL', '--security-opt=no-new-privileges:true']
    for cap in ('CHOWN', 'DAC_OVERRIDE', 'FOWNER', 'FSETID', 'SETGID', 'SETUID', 'NET_BIND_SERVICE', 'KILL'):
        caps.append('--cap-add=' + cap)
    return docker('run', '-d', '--name', name, '--network', network, *caps, *args)


def ready(name):
    for _ in range(60):
        state = json.loads(docker('inspect', name))[0]['State']
        if state.get('Health', {}).get('Status') == 'healthy':
            return
        if not state['Running']:
            raise AssertionError(docker('logs', name))
        time.sleep(1)
    raise AssertionError(docker('logs', name))


try:
    if supplied_image:
        docker('image', 'inspect', image)
    else:
        docker('build', '-t', image, '.')
    docker('network', 'create', '--internal', network)
    docker('volume', 'create', volume)
    docker('volume', 'create', fixtures)
    mock = prefix + '-mock'
    launch(mock, '-e', f'MOCK_HOSTNAME={mock}', '-v', f'{fixtures}:/fixtures', '--entrypoint', 'python3', image, '-u', '-c', (root / 'tests/mock_smtp.py').read_text())
    client = prefix + '-client'
    launch(client, '--entrypoint', 'sleep', image, 'infinity')
    address = json.loads(docker('inspect', client))[0]['NetworkSettings']['Networks'][network]['IPAddress']
    relay = prefix + '-relay'
    common = ['-e', 'SMTP_HOSTNAME=smtp01.example.local', '-e', 'MAIL_DOMAIN=example.com',
              '-e', 'RELAY_PORT=25', '-e', 'RELAY_AUTH_ENABLED=false', '-e', 'OUTBOUND_TLS_LEVEL=may',
              '-e', f'RELAY_HOST={mock}', '-e', 'SMTP_AUTH_USERNAME=relay',
              '-e', 'SMTP_AUTH_PASSWORD=test$!\\, password']
    launch(relay, *common, '-e', f'TRUSTED_NETWORKS={address}/32', '-e', 'SMTP_AUTH_ENABLED=true',
           '-v', f'{volume}:/var/spool/postfix', image)
    ready(relay)
    print(docker('exec', relay, 'postconf', '-n'))
    docker('exec', relay, 'postfix', 'check')
    probe = (root / 'tests/probe.py').read_text()
    print(docker('exec', client, 'python3', '-c', probe, relay, 'trusted'))
    for _ in range(30):
        if docker('exec', mock, 'sh', '-c', 'test -f /tmp/messages && cat /tmp/messages || true').count('relay test') >= 2:
            break
        time.sleep(1)
    else:
        raise AssertionError('Mock upstream did not receive messages')
    # The same client must be rejected when it is outside mynetworks.
    untrusted = prefix + '-untrusted'
    launch(untrusted, *common, '-e', 'ALLOW_EMPTY_TRUSTED_NETWORKS=true', '-e', 'SMTP_AUTH_ENABLED=true', image)
    ready(untrusted)
    print(docker('exec', client, 'python3', '-c', probe, untrusted, 'untrusted'))
    disabled = prefix + '-disabled'
    launch(disabled, *common, '-e', 'ALLOW_EMPTY_TRUSTED_NETWORKS=true', image)
    ready(disabled)
    print(docker('exec', client, 'python3', '-c', probe, disabled, 'disabled'))
    # Default upstream port/auth/TLS, including secret-file precedence and special characters.
    upstream = prefix + '-upstream'
    auth_args = ['-e', 'SMTP_HOSTNAME=smtp01.example.local', '-e', 'MAIL_DOMAIN=example.com',
                 '-e', f'RELAY_HOST={mock}', '-e', f'TRUSTED_NETWORKS={address}/32',
                 '-e', 'RELAY_AUTH_USERNAME=relay@example.com', '-e', 'RELAY_AUTH_PASSWORD=wrong',
                 '-e', 'OUTBOUND_TLS_CA_FILE=/fixtures/ca.crt', '-v', f'{fixtures}:/fixtures:ro']
    launch(upstream, *auth_args, '-e', 'RELAY_AUTH_PASSWORD_FILE=/fixtures/password', image)
    ready(upstream)
    send = "import smtplib,sys; s=smtplib.SMTP(sys.argv[1]); s.sendmail('test@example.com','test@example.net','Subject: '+sys.argv[2]+'\\r\\n\\r\\ntest'); s.quit()"
    docker('exec', client, 'python3', '-c', send, upstream, 'upstream-auth-success')
    for _ in range(30):
        if 'upstream-auth-success' in docker('exec', mock, 'cat', '/tmp/messages'):
            break
        time.sleep(1)
    else:
        raise AssertionError(docker('logs', upstream))
    assert 'AUTH_OK' in docker('logs', mock)
    docker('exec', upstream, 'python3', '-c', "from pathlib import Path; p=Path('/etc/postfix/relay_passwd.db'); assert p.stat().st_mode & 0o777 == 0o600; assert not p.with_suffix('').exists()")
    bad = prefix + '-bad-password'
    launch(bad, *auth_args, image)
    ready(bad)
    docker('exec', client, 'python3', '-c', send, bad, 'must-not-deliver')
    for _ in range(30):
        if 'AUTH_FAILED' in docker('logs', mock):
            break
        time.sleep(1)
    else:
        raise AssertionError('Expected upstream authentication rejection')
    assert 'must-not-deliver' not in docker('exec', mock, 'cat', '/tmp/messages')
    assert docker('exec', bad, 'postqueue', '-j')
    for suffix, options, reason in [
        ('untrusted-ca', ['-e', 'OUTBOUND_TLS_CA_FILE='], 'certificate verification failed'),
        ('no-starttls', ['-e', 'RELAY_PORT=25'], 'TLS is required'),
    ]:
        name = prefix + '-' + suffix
        launch(name, *auth_args, '-e', 'RELAY_AUTH_PASSWORD_FILE=/fixtures/password', *options, image)
        ready(name)
        docker('exec', client, 'python3', '-c', send, name, suffix)
        for _ in range(30):
            logs = docker('logs', name)
            if reason.lower() in logs.lower() and 'status=deferred' in logs:
                break
            time.sleep(1)
        else:
            raise AssertionError(logs)
        assert suffix not in docker('exec', mock, 'cat', '/tmp/messages')
        assert docker('exec', name, 'postqueue', '-j')
    # Queue a message while upstream is down and verify it survives recreation.
    docker('stop', mock)
    print(docker('exec', client, 'python3', '-c', probe, relay, 'trusted'))
    before = docker('exec', relay, 'postqueue', '-j')
    assert before, 'Expected a deferred queue'
    docker('stop', '-t', '60', relay)
    docker('rm', relay); containers.remove(relay)
    launch(relay, *common, '-e', f'TRUSTED_NETWORKS={address}/32', '-e', 'SMTP_AUTH_ENABLED=true',
           '-v', f'{volume}:/var/spool/postfix', image)
    ready(relay)
    after = docker('exec', relay, 'postqueue', '-j')
    assert {json.loads(x)['queue_id'] for x in before.splitlines()} <= {json.loads(x)['queue_id'] for x in after.splitlines()}
    print('Integration passed: ports, relay ACLs, TLS/AUTH, upstream authentication and TLS failures, delivery, queue persistence')
finally:
    for name in reversed(containers):
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL)
    resources = [('volume', volume), ('volume', fixtures), ('network', network)]
    if not supplied_image:
        resources.append(('image', image))
    for resource, name in resources:
        subprocess.run(['docker', resource, 'rm', name], stdout=subprocess.DEVNULL)
