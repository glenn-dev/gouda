"""Safe operational HTTP logs and explicit local-write secret redaction."""

import logging
import re

from django.urls import Resolver404, resolve
from django.views.debug import ExceptionReporter, SafeExceptionReporterFilter


_ROUTES = frozenset({
    "account-discovery", "category-discovery", "canonical-movement-report",
    "classification-write-capability", "movement-classification",
    "financial-import-capability", "santander-current-account-import",
})
_METHODS = frozenset({"GET", "POST", "PATCH", "PUT", "DELETE", "HEAD", "OPTIONS"})


class SafeHttpLogFilter(logging.Filter):
    def filter(self, record):
        if not record.name.startswith(("django.server", "django.request", "django.security")):
            return True
        request = getattr(record, "request", None)
        method = getattr(request, "method", None)
        path = getattr(request, "path_info", "")
        # django.server's request is a socket; its positional request line is
        # inspected only to derive allowlisted fields, never rendered verbatim.
        if record.name == "django.server" and isinstance(record.args, tuple) and record.args:
            line = record.args[0]
            if isinstance(line, str):
                parts = line.split(" ")
                if len(parts) == 3:
                    method, path = parts[:2]
        try:
            route = resolve(path.split("?", 1)[0]).url_name
        except (Resolver404, ValueError):
            route = None
        route = route if route in _ROUTES else "unmatched"
        method = method if method in _METHODS else "OTHER"
        status = getattr(record, "status_code", None)
        status = status if type(status) is int and 100 <= status <= 599 else 500
        record.msg = "http method=%s route=%s status=%s"
        record.args = (method, route, status)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        record.request = None
        return True


class ClassificationExceptionReporterFilter(SafeExceptionReporterFilter):
    hidden_settings = re.compile(
        SafeExceptionReporterFilter.hidden_settings.pattern
        + "|HTTP_X_GOUDA_CLASSIFICATION_WRITE|HTTP_X_GOUDA_FINANCIAL_IMPORT"
        + "|WRITE_CAPABILITY|IMPORT_CAPABILITY", re.I,
    )

    def get_traceback_frame_variables(self, request, tb_frame):
        if (
            getattr(request, "gouda_classification_write", False)
            or getattr(request, "gouda_financial_import", False)
        ):
            return [("locals", self.cleansed_substitute)]
        return super().get_traceback_frame_variables(request, tb_frame)


class ClassificationExceptionReporter(ExceptionReporter):
    # Defense in depth if a later response/middleware failure reaches Django's
    # reporter: no raw URL, JSON body, header, exception value, or frame locals.
    def get_traceback_text(self):
        if getattr(self.request, "gouda_classification_write", False):
            return "classification internal_error"
        if getattr(self.request, "gouda_financial_import", False):
            return "financial_import internal_error"
        return super().get_traceback_text()

    def get_traceback_html(self):
        if getattr(self.request, "gouda_classification_write", False):
            return "classification internal_error"
        if getattr(self.request, "gouda_financial_import", False):
            return "financial_import internal_error"
        return super().get_traceback_html()
