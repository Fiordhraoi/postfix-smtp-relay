import smtplib
import subprocess
import sys

try:
    subprocess.run(['postfix', 'status'], check=True, capture_output=True, timeout=3)
    for port in (25, 587):
        with smtplib.SMTP('127.0.0.1', port, timeout=2) as smtp:
            assert smtp.ehlo()[0] == 250
            assert smtp.has_extn('starttls')
except Exception:
    sys.exit(1)
