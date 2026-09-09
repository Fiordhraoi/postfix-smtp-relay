import base64
import smtplib
import ssl
import sys

host, mode = sys.argv[1:]
context = ssl._create_unverified_context()  # Only this isolated test uses a self-signed cert.
password = 'test$!\\, password'
for port in (25, 587):
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.ehlo()
        assert smtp.has_extn('starttls')
        assert not smtp.has_extn('auth')
        assert smtp.esmtp_features['size'] == '52428800'
        assert smtp.docmd('AUTH', 'PLAIN ' + base64.b64encode(b'\0relay\0bad').decode())[0] >= 500
        smtp.mail('test@example.com')
        code, reply = smtp.rcpt('recipient@example.net')
        assert code == 250 if mode == 'trusted' else code == 554, (code, reply)
        smtp.rset()
        if mode == 'trusted':
            smtp.sendmail('test@example.com', ['recipient@example.net'], 'Subject: anonymous\r\n\r\nanonymous relay test\r\n')
        smtp.starttls(context=context); smtp.ehlo()
        if mode == 'disabled':
            assert not smtp.has_extn('auth')
            continue
        assert {'PLAIN', 'LOGIN'} <= set(smtp.esmtp_features['auth'].split())
        try:
            smtp.login('relay', 'wrong')
            raise AssertionError('Bad password accepted')
        except smtplib.SMTPAuthenticationError:
            pass
        smtp.user, smtp.password = 'relay', password
        # Exercise both mechanisms independently, one on each port.
        mechanism = 'PLAIN' if port == 25 else 'LOGIN'
        smtp.auth(mechanism, smtp.auth_plain if port == 25 else smtp.auth_login)
        smtp.sendmail('test@example.com', ['recipient@example.net'], 'Subject: integration\r\n\r\nrelay test\r\n')
print('SMTP probes passed:', mode)
