"""Minimal isolated SMTP sink; no forwarding and no external services."""
import socketserver
import ssl
import subprocess
import threading
import base64
import os
from pathlib import Path


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        authenticated = False
        encrypted = False
        self.wfile.write(b'220 mock ESMTP\r\n')
        while line := self.rfile.readline():
            command = line.split(b' ', 1)[0].strip().upper()
            if command == b'EHLO' and self.server.server_address[1] == 587:
                self.wfile.write(b'250-mock\r\n250 AUTH PLAIN LOGIN\r\n' if encrypted else b'250-mock\r\n250 STARTTLS\r\n')
            elif command == b'STARTTLS':
                self.wfile.write(b'220 ready\r\n')
                self.connection = context.wrap_socket(self.connection, server_side=True)
                self.rfile = self.connection.makefile('rb')
                self.wfile = self.connection.makefile('wb', buffering=0)
                encrypted = True
            elif command == b'AUTH':
                parts = line.strip().split()
                if parts[1].upper() == b'LOGIN':
                    self.wfile.write(b'334 VXNlcm5hbWU6\r\n')
                    username = base64.b64decode(self.rfile.readline().strip())
                    self.wfile.write(b'334 UGFzc3dvcmQ6\r\n')
                    password = base64.b64decode(self.rfile.readline().strip())
                    credentials = [username, password]
                else:
                    if len(parts) < 3:
                        self.wfile.write(b'334 \r\n')
                        parts.append(self.rfile.readline().strip())
                    credentials = base64.b64decode(parts[2]).split(b'\0')[-2:]
                authenticated = encrypted and credentials == [b'relay@example.com', b'upstream$!\\,: pass']
                self.wfile.write(b'235 authenticated\r\n' if authenticated else b'535 bad credentials\r\n')
                print('AUTH_OK' if authenticated else 'AUTH_FAILED', flush=True)
            elif command == b'MAIL' and self.server.server_address[1] == 587 and not authenticated:
                self.wfile.write(b'530 authentication required\r\n')
            elif command == b'DATA':
                self.wfile.write(b'354 continue\r\n')
                message = bytearray()
                while True:
                    data = self.rfile.readline()
                    if not data or data == b'.\r\n':
                        break
                    message.extend(data)
                with Path('/tmp/messages').open('ab') as output:
                    output.write(message)
                self.wfile.write(b'250 queued\r\n')
            elif command == b'QUIT':
                self.wfile.write(b'221 bye\r\n'); break
            else:
                self.wfile.write(b'250 mock\r\n')


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=' + os.environ['MOCK_HOSTNAME'], '-addext',
                'subjectAltName=DNS:' + os.environ['MOCK_HOSTNAME'], '-keyout', '/fixtures/key.pem',
                '-out', '/fixtures/ca.crt'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
Path('/fixtures/password').write_text('upstream$!\\,: pass\n')
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('/fixtures/ca.crt', '/fixtures/key.pem')
threading.Thread(target=Server(('0.0.0.0', 587), Handler).serve_forever, daemon=True).start()
Server(('0.0.0.0', 25), Handler).serve_forever()
