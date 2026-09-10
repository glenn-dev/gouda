"""Strict ADR-0013 HTTP boundary for one private Santander XLSX import."""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID

from django.core.exceptions import DisallowedHost
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from gouda.local_delivery import (
    LocalDeliveryBootstrapError,
    require_active_local_delivery_runtime,
)
from gouda.local_financial_import import (
    FinancialImportError,
    IMPORT_HOST,
    IMPORT_ORIGIN,
    require_financial_import_runtime,
)
from .classification_api import _accepts_json
from .models import ImportBatch
from .services.account_access import AccountAccessServiceError, validate_principal_context
from .services.financial_import_access import (
    AdmittedStatement,
    FinancialImportAccessError,
    import_authorized_santander_current_account_xlsx,
)
from .services.santander_import import (
    ACCOUNT_CONTEXT_CHANGED,
    MATERIALIZATION_DATABASE_ERROR,
    MATERIALIZATION_FAILED,
    MATERIALIZATION_INTEGRITY_ERROR,
    SOURCE_KIND_CONFLICT,
    SOURCE_VARIANT_UNSUPPORTED,
    SantanderImportOperationalError,
    SantanderImportServiceError,
)
from .xlsx_admission import XlsxAdmissionError, admit_xlsx_package


MAX_STATEMENT_BYTES = 5 * 1024 * 1024
MAX_MULTIPART_BYTES = MAX_STATEMENT_BYTES + 16 * 1024
IMPORT_CAPABILITY_HEADER = "HTTP_X_GOUDA_FINANCIAL_IMPORT"

_ERROR_STATUS = {
    "local_delivery_not_active": 503,
    "financial_import_not_enabled": 403,
    "host_not_allowed": 400,
    "method_not_allowed": 405,
    "origin_not_allowed": 403,
    "import_capability_invalid": 403,
    "principal_context_invalid": 403,
    "not_acceptable": 406,
    "query_parameters_not_allowed": 400,
    "unsupported_media_type": 415,
    "malformed_json": 400,
    "request_body_invalid": 400,
    "account_selector_invalid": 400,
    "account_not_accessible": 404,
    "account_source_incompatible": 409,
    "statement_missing": 400,
    "request_body_too_large": 413,
    "statement_too_large": 413,
    "import_busy": 429,
    "statement_resource_limit": 413,
    "xlsx_invalid": 422,
    "source_unrecognized": 422,
    "statement_not_importable": 422,
    "account_context_changed": 409,
    "source_kind_conflict": 409,
    "import_persistence_failed": 503,
    "internal_error": 500,
}
_logger = logging.getLogger("gouda.financial_import")
_BOUNDARY_RE = re.compile(
    r"multipart/form-data\s*;\s*boundary=(?:\"([0-9A-Za-z'()+_,./:=? -]{1,70})\"|([0-9A-Za-z'()+_,./:=?-]{1,70}))",
    re.IGNORECASE,
)
_ALLOWED_PART_MEDIA = frozenset(
    {
        "application/octet-stream",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
_SOURCE_UNRECOGNIZED = frozenset(
    {"ambiguous_statement_worksheets", "movement_header_not_found", SOURCE_VARIANT_UNSUPPORTED}
)
_STATEMENT_NOT_IMPORTABLE = frozenset(
    {
        "formula_unsupported",
        "period_context_ambiguous",
        "period_context_invalid",
        "period_context_missing",
        "money_not_finite",
        "money_scale_exceeded",
        "money_precision_exceeded",
        "movement_amount_zero",
    }
)
_PERSISTENCE_FAILURES = frozenset(
    {
        "registration_database_error",
        "registration_failed",
        MATERIALIZATION_INTEGRITY_ERROR,
        MATERIALIZATION_DATABASE_ERROR,
        MATERIALIZATION_FAILED,
        "fatal_compensation_conflict",
        "fatal_compensation_failed",
    }
)


def _fail(code):
    raise FinancialImportError(code)


def _uuid(value):
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError):
        _fail("account_selector_invalid")
    if str(parsed) != value:
        _fail("account_selector_invalid")
    return parsed


def _read_bounded(request, limit):
    chunks = []
    remaining = limit + 1
    while remaining:
        chunk = request.read(min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > limit:
        _fail("request_body_too_large")
    return raw


def _json_body(request):
    if not _accepts_json(request.META.get("HTTP_ACCEPT")):
        _fail("not_acceptable")
    if request.META.get("QUERY_STRING", ""):
        _fail("query_parameters_not_allowed")
    if (
        re.fullmatch(
            r'application/json(?:\s*;\s*charset=(?:utf-8|"utf-8"))?',
            request.META.get("CONTENT_TYPE", ""),
            re.IGNORECASE,
        )
        is None
        or request.META.get("HTTP_CONTENT_ENCODING", "identity") != "identity"
    ):
        _fail("unsupported_media_type")
    _validate_framing(request, 1024)
    raw = _read_bounded(request, 1024)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_json_object,
            parse_constant=lambda _: _fail("malformed_json"),
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, FinancialImportError):
            raise
        _fail("malformed_json")
    if type(value) is not dict or value:
        _fail("request_body_invalid")
    return value


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail("request_body_invalid")
        value[key] = item
    return value


def _validate_framing(request, limit):
    if request.META.get("HTTP_TRANSFER_ENCODING"):
        _fail("request_body_invalid")
    declared = request.META.get("CONTENT_LENGTH")
    if declared not in (None, ""):
        if not declared.isascii() or not declared.isdecimal() or declared.startswith("0"):
            _fail("request_body_invalid")
        if int(declared) > limit:
            _fail("request_body_too_large")


def _validate_import_metadata(request):
    if not _accepts_json(request.META.get("HTTP_ACCEPT")):
        _fail("not_acceptable")
    if request.META.get("QUERY_STRING", ""):
        _fail("query_parameters_not_allowed")
    if request.META.get("HTTP_CONTENT_ENCODING", "identity") != "identity":
        _fail("unsupported_media_type")
    _validate_framing(request, MAX_MULTIPART_BYTES)
    value = request.META.get("CONTENT_TYPE", "")
    match = _BOUNDARY_RE.fullmatch(value)
    if match is None:
        _fail("unsupported_media_type")
    boundary = match.group(1) or match.group(2)
    if not boundary or boundary.endswith(" "):
        _fail("unsupported_media_type")
    return boundary.encode("ascii")


def _multipart_statement(request, boundary):
    raw = _read_bounded(request, MAX_MULTIPART_BYTES)
    opening = b"--" + boundary + b"\r\n"
    closing = b"\r\n--" + boundary + b"--"
    if not raw.startswith(opening):
        _fail("statement_missing" if raw in {b"", b"--" + boundary + b"--\r\n"} else "request_body_invalid")
    if raw.endswith(closing + b"\r\n"):
        part = raw[len(opening) : -len(closing + b"\r\n")]
    elif raw.endswith(closing):
        part = raw[len(opening) : -len(closing)]
    else:
        _fail("request_body_invalid")
    if closing in part or b"\r\n--" + boundary + b"\r\n" in part:
        _fail("request_body_invalid")
    if b"\r\n\r\n" not in part:
        _fail("request_body_invalid")
    header_block, content = part.split(b"\r\n\r\n", 1)
    if len(header_block) > 16 * 1024 or not header_block:
        _fail("request_body_invalid")
    headers = _part_headers(header_block)
    disposition = headers.get("content-disposition")
    if disposition is None:
        _fail("statement_missing")
    filename = _content_disposition_filename(disposition)
    part_media = headers.get("content-type")
    if part_media is not None and part_media.lower() not in _ALLOWED_PART_MEDIA:
        _fail("unsupported_media_type")
    if not content:
        _fail("statement_missing")
    if len(content) > MAX_STATEMENT_BYTES:
        _fail("statement_too_large")
    admit_xlsx_package(content)
    return AdmittedStatement(content=content, original_filename=filename)


def _part_headers(raw):
    if b"\n" in raw.replace(b"\r\n", b""):
        _fail("request_body_invalid")
    result = {}
    for line in raw.split(b"\r\n"):
        if line[:1] in {b" ", b"\t"} or b":" not in line:
            _fail("request_body_invalid")
        name, value = line.split(b":", 1)
        try:
            name = name.decode("ascii").lower()
            value = value.decode("utf-8").strip()
        except UnicodeError:
            _fail("request_body_invalid")
        if name not in {"content-disposition", "content-type"} or name in result:
            _fail("request_body_invalid")
        result[name] = value
    return result


def _content_disposition_filename(value):
    segments = _split_parameters(value)
    if not segments or segments[0].lower() != "form-data" or len(segments) != 3:
        _fail("request_body_invalid")
    parameters = {}
    for segment in segments[1:]:
        if "=" not in segment:
            _fail("request_body_invalid")
        name, raw_value = segment.split("=", 1)
        name = name.strip().lower()
        if name not in {"name", "filename"} or name in parameters:
            _fail("request_body_invalid")
        parameters[name] = _quoted_value(raw_value.strip())
    if parameters.get("name") != "statement" or not parameters.get("filename"):
        _fail("statement_missing")
    return parameters["filename"]


def _split_parameters(value):
    segments = []
    start = 0
    quoted = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
        elif quoted and character == "\\":
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif character == ";" and not quoted:
            segments.append(value[start:index].strip())
            start = index + 1
    if quoted or escaped:
        _fail("request_body_invalid")
    segments.append(value[start:].strip())
    return segments


def _quoted_value(value):
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        _fail("request_body_invalid")
    result = []
    escaped = False
    for character in value[1:-1]:
        if escaped:
            result.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"' or ord(character) < 32 or ord(character) == 127:
            _fail("request_body_invalid")
        else:
            result.append(character)
    if escaped:
        _fail("request_body_invalid")
    return "".join(result)


def _project_result(batch):
    batch = ImportBatch.objects.select_related("duplicate_of").get(pk=batch.pk)
    target = batch
    duplicate_of = None
    created = batch.parsed_count
    if batch.status == ImportBatch.Status.DUPLICATE:
        target = batch.duplicate_of
        if (
            target is None
            or target.account_id != batch.account_id
            or target.source_artifact_id != batch.source_artifact_id
            or target.source_kind != batch.source_kind
            or target.status not in {
                ImportBatch.Status.ACCEPTED,
                ImportBatch.Status.PARTIAL,
                ImportBatch.Status.REJECTED,
            }
        ):
            _fail("internal_error")
        duplicate_of = str(target.pk)
        created = 0
    elif batch.status == ImportBatch.Status.FATAL:
        _fail(_map_fatal_code(batch.failure_code))
    elif batch.status not in {
        ImportBatch.Status.ACCEPTED,
        ImportBatch.Status.PARTIAL,
        ImportBatch.Status.REJECTED,
    }:
        _fail("internal_error")
    if (
        target.period_start is None
        or target.period_end is None
        or target.reconciliation_status not in ImportBatch.ReconciliationStatus.values
    ):
        _fail("internal_error")
    return {
        "account_id": str(batch.account_id),
        "batch_id": str(batch.pk),
        "status": batch.status,
        "duplicate_of": duplicate_of,
        "created_movement_count": created,
        "statement": {
            "status": target.status,
            "source_row_count": target.parsed_count + target.ignored_count + target.rejected_count,
            "parsed_count": target.parsed_count,
            "ignored_count": target.ignored_count,
            "rejected_count": target.rejected_count,
            "reconciliation_status": target.reconciliation_status,
            "period_start": target.period_start.isoformat(),
            "period_end": target.period_end.isoformat(),
        },
    }


def _map_fatal_code(code):
    if code == "xlsx_invalid":
        return "xlsx_invalid"
    if code in _SOURCE_UNRECOGNIZED:
        return "source_unrecognized"
    if code in _STATEMENT_NOT_IMPORTABLE:
        return "statement_not_importable"
    if code == ACCOUNT_CONTEXT_CHANGED:
        return "account_context_changed"
    if code == SOURCE_KIND_CONFLICT:
        return "source_kind_conflict"
    if code in _PERSISTENCE_FAILURES:
        return "import_persistence_failed"
    return "internal_error"


@method_decorator(csrf_exempt, name="dispatch")
class _FinancialImportView(View):
    allowed_method = "POST"
    requires_capability = False

    def dispatch(self, request, *args, **kwargs):
        request.gouda_financial_import = True
        try:
            delivery = require_active_local_delivery_runtime()
            runtime = require_financial_import_runtime()
            try:
                host = request.get_host()
            except DisallowedHost:
                _fail("host_not_allowed")
            if "HTTP_HOST" not in request.META or host != IMPORT_HOST:
                _fail("host_not_allowed")
            if request.method != self.allowed_method:
                _fail("method_not_allowed")
            if request.META.get("HTTP_ORIGIN") != IMPORT_ORIGIN:
                _fail("origin_not_allowed")
            grant = None
            if self.requires_capability:
                grant = runtime.verify_capability(request.META.get(IMPORT_CAPABILITY_HEADER))
            principal = delivery.trusted_principal_context()
            validate_principal_context(principal)
            payload = self.execute(request, principal, grant, runtime, **kwargs)
            response = JsonResponse(payload)
        except (
            LocalDeliveryBootstrapError,
            FinancialImportError,
            FinancialImportAccessError,
            AccountAccessServiceError,
            XlsxAdmissionError,
            SantanderImportServiceError,
        ) as error:
            code = _public_error_code(error)
            response = JsonResponse({"code": code}, status=_ERROR_STATUS[code])
        except Exception:
            _logger.error("financial_import internal_error")
            response = JsonResponse({"code": "internal_error"}, status=500)
        response["Cache-Control"] = "no-store, no-cache, max-age=0"
        response["Pragma"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        if response.status_code == 405:
            response["Allow"] = self.allowed_method
        if request.method == "HEAD":
            response.content = b""
        return response


class FinancialImportCapabilityView(_FinancialImportView):
    def execute(self, request, principal, grant, runtime):
        _json_body(request)
        return {"import_capability": runtime.bootstrap_capability()}


class SantanderCurrentAccountImportView(_FinancialImportView):
    requires_capability = True

    def execute(self, request, principal, grant, runtime, account_uuid):
        boundary = _validate_import_metadata(request)
        account_id = _uuid(account_uuid)
        batch = import_authorized_santander_current_account_xlsx(
            principal_context=principal,
            import_grant=grant,
            account_selector=account_id,
            admitted_statement_loader=lambda: _multipart_statement(request, boundary),
            upload_slot=runtime.acquire_upload_slot,
        )
        return _project_result(batch)


def _public_error_code(error):
    code = getattr(error, "code", "internal_error")
    if isinstance(error, SantanderImportOperationalError):
        code = "import_persistence_failed" if code in _PERSISTENCE_FAILURES else "internal_error"
    elif isinstance(error, SantanderImportServiceError):
        code = {
            "filename_invalid": "request_body_invalid",
            "account_not_found": "account_not_accessible",
            "account_kind_unsupported": "account_source_incompatible",
            "account_orientation_unsupported": "account_source_incompatible",
            "account_currency_invalid": "account_source_incompatible",
        }.get(code, code)
    return code if code in _ERROR_STATUS else "internal_error"
