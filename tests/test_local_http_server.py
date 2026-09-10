import socket
import threading
from unittest.mock import patch

from django.conf import settings
from django.core.servers.basehttp import WSGIRequestHandler
from django.core.wsgi import get_wsgi_application
from django.test import SimpleTestCase

from gouda.ledger.management.commands.runlocal import Command
from gouda.local_delivery import run_validated_local_delivery


class LocalHttpTransportTests(SimpleTestCase):
    def exchange(self, headers, body=b"", origin=b"http://127.0.0.1:5173", host=b"127.0.0.1:5173"):
        server = Command.server_cls(("127.0.0.1", 0), WSGIRequestHandler)
        server.set_app(get_wsgi_application())
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        client = socket.create_connection(server.server_address, timeout=1)
        client.settimeout(0.4)
        try:
            client.sendall(b"POST /api/v1/local/financial-import-capability/ HTTP/1.1\r\n"
                           + (b"Host: " + host + b"\r\n" if host is not None else b"")
                           + (b"Origin: " + origin + b"\r\n" if origin is not None else b"")
                           +
                           b"Content-Type: application/json\r\n" + headers + b"\r\n" + body)
            response = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    return response
                response += chunk
        finally:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
            thread.join(timeout=2)
            server.server_close()

    def run_enabled(self, operation):
        with patch.dict(settings.DATABASES["default"], {"NAME": "gouda_private"}):
            return run_validated_local_delivery(
                bind_host="127.0.0.1", port="8000", enable_financial_imports=True,
                financial_import_origin="http://127.0.0.1:5173", server_runner=lambda _: operation(),
            )

    def test_denied_large_body_is_not_drained_after_response(self):
        response = self.run_enabled(lambda: self.exchange(b"Content-Length: 100000000\r\n"))
        self.assertIn(b"413", response.split(b"\r\n", 1)[0])

    def test_duplicate_length_and_transfer_encoding_cannot_bootstrap(self):
        for headers in (b"Content-Length: 2\r\nContent-Length: 2\r\n",
                        b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n"):
            response = self.run_enabled(lambda: self.exchange(headers, b"{}"))
            self.assertIn(b"400", response.split(b"\r\n", 1)[0])
            self.assertNotIn(b"import_capability", response)

    def test_direct_wsgi_preserves_security_header_multiplicity(self):
        for extra in (b"Host: 127.0.0.1:5173\r\n", b"Origin: http://127.0.0.1:5173\r\n"):
            response = self.run_enabled(lambda: self.exchange(b"Content-Length: 2\r\n" + extra, b"{}"))
            self.assertNotIn(b"200", response.split(b"\r\n", 1)[0])
            self.assertNotIn(b"import_capability", response)
        for origin in (None, b"null", b"https://evil.invalid", b"HTTP://127.0.0.1:5173", b"http://127.0.0.1:5173/"):
            response = self.run_enabled(lambda: self.exchange(b"Content-Length: 2\r\n", b"{}", origin=origin))
            self.assertIn(b"403", response.split(b"\r\n", 1)[0])
        response = self.run_enabled(lambda: self.exchange(
            b"Content-Length: 2\r\nX-Forwarded-Host: 127.0.0.1:5173\r\n", b"{}", host=b"127.0.0.1:8000"))
        self.assertIn(b"400", response.split(b"\r\n", 1)[0])
