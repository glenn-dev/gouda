"""The runlocal WSGI transport: bounded reads and unambiguous raw headers."""

from wsgiref.simple_server import ServerHandler as StandardServerHandler

from django.core.servers.basehttp import ServerHandler, WSGIRequestHandler, WSGIServer


class LocalServerHandler(ServerHandler):
    def cleanup_headers(self):
        # No keep-alive means no need to consume an untrusted remainder. Django
        # 4.2's ServerHandler.close() otherwise reads it all into one bytes value,
        # including after a denial and outside the application admission slot.
        self.headers["Connection"] = "close"
        super().cleanup_headers()

    def close(self):
        StandardServerHandler.close(self)


class LocalRequestHandler(WSGIRequestHandler):
    def get_environ(self):
        environ = super().get_environ()
        # wsgiref preserves Host/Origin multiplicity but silently selects the
        # first Content-Length/Type. Preserve these as invalid combined values.
        for name, key in (("Content-Length", "CONTENT_LENGTH"), ("Content-Type", "CONTENT_TYPE")):
            values = self.headers.get_all(name, [])
            if len(values) > 1:
                environ[key] = ",".join(values)
        return environ

    def handle_one_request(self):
        # Pinned Django 4.2 handler, with only the ServerHandler choice changed.
        self.raw_requestline = self.rfile.readline(65537)
        if len(self.raw_requestline) > 65536:
            self.requestline = ""
            self.request_version = ""
            self.command = ""
            self.send_error(414)
            return
        if not self.parse_request():
            return
        handler = LocalServerHandler(self.rfile, self.wfile, self.get_stderr(), self.get_environ())
        handler.request_handler = self
        handler.run(self.server.get_app())


class LocalWSGIServer(WSGIServer):
    def __init__(self, server_address, request_handler_class, **kwargs):
        super().__init__(server_address, LocalRequestHandler, **kwargs)

    def serve_forever(self, *args, **kwargs):
        # runserver enables daemon threads; orderly exit must instead drain the
        # admitted operation before the launcher revokes its runtime.
        self.daemon_threads = False
        try:
            return super().serve_forever(*args, **kwargs)
        finally:
            self.server_close()
