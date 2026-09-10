import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import validate, render


class ConfigurationTests(unittest.TestCase):
    def env(self, **overrides):
        env = dict(SMTP_HOSTNAME='smtp01.example.local', MAIL_DOMAIN='example.com',
                   RELAY_HOST='mx.example.com', TRUSTED_NETWORKS='10.10.0.0/16,10.20.0.0/16,2001:db8::/32',
                   RELAY_AUTH_ENABLED='false')
        env.update(overrides)
        return env

    def test_generation(self):
        text = render(validate(self.env()))
        for expected in ('[2001:db8::]/32', '10.10.0.0/16, 10.20.0.0/16',
                         'reject_unauth_destination', 'smtp_sasl_auth_enable = no',
                         'smtpd_tls_auth_only = yes', 'message_size_limit = 52428800',
                         'smtpd_sasl_auth_enable = no', 'mydestination = \n', 'relay_domains = \n'):
            self.assertIn(expected, text)

    def test_required(self):
        for key in ('SMTP_HOSTNAME', 'MAIL_DOMAIN', 'RELAY_HOST'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                env = self.env(); del env[key]; validate(env)

    def test_invalid(self):
        cases = {'TRUSTED_NETWORKS': ['', '0.0.0.0/0', '::/0', '10.1.2.3/16', 'bad', '10.0.0.0/8,'],
                 'RELAY_PORT': ['0', '65536', '25\n', 'abc'], 'MESSAGE_SIZE_LIMIT': ['0', '-1', 'x'],
                 'SMTP_AUTH_ENABLED': ['yes'], 'ALLOW_EMPTY_TRUSTED_NETWORKS': ['yes'],
                 'OUTBOUND_TLS_LEVEL': ['invalid'], 'SMTP_HOSTNAME': ['x\nmydestination=any', 'a..b'],
                 'RELAY_HOST': ['[mx.example.com]:25', 'a$mydomain'],
                 'TLS_CERT_FILE': ['/missing'], 'SMTP_AUTH_PASSWORD_FILE': ['/does-not-exist']}
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    env = self.env(); env[key] = value; validate(env)

    def test_empty_opt_in(self):
        env = self.env(ALLOW_EMPTY_TRUSTED_NETWORKS='true'); env['TRUSTED_NETWORKS'] = ''
        self.assertEqual(validate(env)['networks'], ['127.0.0.0/8', '[::1]/128'])

    def test_auth(self):
        with self.assertRaises(ValueError):
            validate(self.env(SMTP_AUTH_ENABLED='true'))
        env = self.env(SMTP_AUTH_ENABLED='true', SMTP_AUTH_USERNAME='relay', SMTP_AUTH_PASSWORD='a$!"\\ ,b')
        c = validate(env)
        self.assertIn('smtpd_sasl_auth_enable = yes', render(c))
        self.assertNotIn(c['password'], render(c))

    def test_password_file_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / 'password'
            secret.write_text('special$!\\, password\n')
            c = validate(self.env(SMTP_AUTH_ENABLED='true', SMTP_AUTH_USERNAME='relay',
                                  SMTP_AUTH_PASSWORD='wrong', SMTP_AUTH_PASSWORD_FILE=str(secret)))
            self.assertEqual(c['password'], 'special$!\\, password')
            secret.write_text('two\nlines')
            with self.assertRaises(ValueError):
                validate(self.env(SMTP_AUTH_ENABLED='true', SMTP_AUTH_USERNAME='relay', SMTP_AUTH_PASSWORD_FILE=str(secret)))

    def test_ipv6_relay_and_size(self):
        env = self.env(MESSAGE_SIZE_LIMIT='1024'); env['RELAY_HOST'] = '2001:db8::1'
        text = render(validate(env))
        self.assertIn('relayhost = [IPv6:2001:db8::1]:587', text)
        self.assertIn('message_size_limit = 1024', text)

    def test_upstream_defaults_and_tls(self):
        env = self.env(RELAY_AUTH_USERNAME='relay@example.com', RELAY_AUTH_PASSWORD='a$!\\,: pass')
        del env['RELAY_AUTH_ENABLED']
        c = validate(env)
        text = render(c)
        for value in ('relayhost = [mx.example.com]:587', 'smtp_sasl_auth_enable = yes',
                      'smtp_tls_security_level = secure', 'hash:/etc/postfix/relay_passwd'):
            self.assertIn(value, text)
        self.assertNotIn(c['relay_password'], text)
        for level in ('none', 'may'):
            with self.subTest(level=level), self.assertRaisesRegex(ValueError, 'plaintext fallback'):
                validate(dict(env, OUTBOUND_TLS_LEVEL=level))

    def test_upstream_missing_credentials(self):
        for changes in ({}, {'RELAY_AUTH_USERNAME': 'relay'},
                        {'RELAY_AUTH_USERNAME': 'bad:user', 'RELAY_AUTH_PASSWORD': 'secret'},
                        {'RELAY_AUTH_USERNAME': 'relay', 'RELAY_AUTH_PASSWORD': 'secret\n'},
                        {'RELAY_AUTH_USERNAME': 'relay', 'RELAY_AUTH_PASSWORD': 'secret '},
                        {'RELAY_AUTH_ENABLED': 'yes'}, {'RELAY_AUTH_PASSWORD_FILE': '/missing'},
                        {'OUTBOUND_TLS_CA_FILE': '/missing'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                env = self.env(RELAY_AUTH_ENABLED='true'); env.update(changes); validate(env)

    def test_upstream_secret_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / 'relay-password'
            secret.write_bytes(b'a$!\\,: pass\r\n')
            c = validate(self.env(RELAY_AUTH_ENABLED='true', RELAY_AUTH_USERNAME='relay@example.com',
                                  RELAY_AUTH_PASSWORD='wrong', RELAY_AUTH_PASSWORD_FILE=str(secret)))
            self.assertEqual(c['relay_password'], 'a$!\\,: pass')

    def test_unauthenticated_port25_alternative(self):
        text = render(validate(self.env(RELAY_PORT='25', OUTBOUND_TLS_LEVEL='may')))
        self.assertIn('relayhost = [mx.example.com]:25', text)
        self.assertIn('smtp_sasl_auth_enable = no', text)


if __name__ == '__main__':
    unittest.main()
