"""Minimal isolated SMTP sink; no forwarding and no external services."""
import socketserver
from pathlib import Path


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'220 mock ESMTP\r\n')
        while line := self.rfile.readline():
            command = line.split(b' ', 1)[0].strip().upper()
            if command == b'DATA':
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


Server(('0.0.0.0', 25), Handler).serve_forever()
