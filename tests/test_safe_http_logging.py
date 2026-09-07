import io
import logging
import sys

from django.test import RequestFactory, SimpleTestCase, override_settings

from gouda.safe_http_logging import (
    ClassificationExceptionReporter, ClassificationExceptionReporterFilter, SafeHttpLogFilter,
)
from tests.fixtures.local_classification_write import BOOTSTRAP, HEADERS


class SafeHttpLoggingTests(SimpleTestCase):
    sentinel = "synthetic-capability-must-not-appear"

    def test_access_error_and_security_logs_keep_only_safe_fields(self):
        request = RequestFactory().post(BOOTSTRAP + "?token=" + self.sentinel,
                                       data=self.sentinel, content_type="application/json", **HEADERS)
        for name in ("django.server", "django.request", "django.security.DisallowedHost"):
            record = logging.LogRecord(name, logging.ERROR, __file__, 1, self.sentinel,
                                       (f"POST {BOOTSTRAP}?{self.sentinel} HTTP/1.1", "500", "0"),
                                       (RuntimeError, RuntimeError(self.sentinel), None))
            record.request = request
            record.status_code = 500
            record.stack_info = self.sentinel
            SafeHttpLogFilter().filter(record)
            output = logging.Formatter().format(record)
            self.assertNotIn(self.sentinel, output)
            self.assertIn("classification-write-capability", output)
            self.assertIsNone(record.request)
            self.assertIsNone(record.exc_info)

    @override_settings(DEBUG=True)
    def test_header_bootstrap_field_and_exception_report_are_explicitly_redacted(self):
        reporter_filter = ClassificationExceptionReporterFilter()
        for name in ("HTTP_X_GOUDA_CLASSIFICATION_WRITE", "write_capability"):
            self.assertEqual(reporter_filter.cleanse_setting(name, self.sentinel), reporter_filter.cleansed_substitute)
        request = RequestFactory().post(BOOTSTRAP, data=self.sentinel, content_type="application/json", **HEADERS,
                                       HTTP_X_GOUDA_CLASSIFICATION_WRITE=self.sentinel)
        request.gouda_classification_write = True
        try:
            raise RuntimeError(self.sentinel)
        except RuntimeError:
            reporter = ClassificationExceptionReporter(request, *sys.exc_info())
            self.assertNotIn(self.sentinel, reporter.get_traceback_text())
            self.assertNotIn(self.sentinel, reporter.get_traceback_html())
            self.assertNotIn(self.sentinel, str(reporter_filter.get_traceback_frame_variables(request, sys._getframe())))

    def test_configured_handler_sanitizes_before_emission(self):
        stream = io.StringIO()
        logger = logging.getLogger("django.server")
        handler = logger.handlers[0]
        original = handler.setStream(stream)
        try:
            logger.error('"%s" %s %s', "PATCH /api/" + self.sentinel + " HTTP/1.1", "500", "0", extra={"status_code": 500})
        finally:
            handler.setStream(original)
        self.assertNotIn(self.sentinel, stream.getvalue())
        self.assertIn("method=PATCH", stream.getvalue())
