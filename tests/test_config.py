import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import validate, render


class ConfigurationTests(unittest.TestCase):
    def env(self, **overrides):
        return dict(SMTP_HOSTNAME='smtp01.example.local', MAIL_DOMAIN='example.com',
                    RELAY_HOST='mx.example.com', TRUSTED_NETWORKS='10.10.0.0/16,10.20.0.0/16,2001:db8::/32', **overrides)

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
        self.assertIn('relayhost = [IPv6:2001:db8::1]:25', text)
        self.assertIn('message_size_limit = 1024', text)


if __name__ == '__main__':
    unittest.main()
