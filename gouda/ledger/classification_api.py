"""Strict ADR-0012 HTTP adapter; security gates precede parsing and ORM work."""

import json
import logging
import re
from urllib.request import parse_http_list
from uuid import UUID

from django.core.exceptions import DisallowedHost
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from gouda.local_delivery import (
    LocalDeliveryBootstrapError, require_active_local_delivery_runtime,
)
from gouda.local_classification_write import (
    ClassificationWriteError, WRITE_HOST, WRITE_ORIGIN,
    require_classification_write_runtime,
)
from .api import _serialize_classification
from .services.account_access import AccountAccessServiceError, validate_principal_context
from .services.classification_access import classify_authorized_movement
from .services.movement_classification import MovementClassificationServiceError


_ERROR_STATUS = {
    "local_delivery_not_active": 503,
    "mutation_not_enabled": 403,
    "host_not_allowed": 400,
    "origin_not_allowed": 403,
    "write_capability_invalid": 403,
    "principal_context_invalid": 403,
    "account_selector_invalid": 400,
    "account_not_accessible": 404,
    "movement_id_invalid": 400,
    "movement_not_found": 404,
    "category_id_invalid": 400,
    "category_not_found": 404,
    "category_inactive": 409,
    "expected_revision_invalid": 400,
    "classification_not_present": 409,
    "classification_revision_conflict": 409,
    "classification_revision_exhausted": 409,
    "malformed_json": 400,
    "request_body_invalid": 400,
    "query_parameters_not_allowed": 400,
    "request_body_too_large": 413,
    "method_not_allowed": 405,
    "not_acceptable": 406,
    "unsupported_media_type": 415,
    "internal_error": 500,
}
_logger = logging.getLogger("gouda.classification")
_JSON_NON_INTEGER = object()


def _fail(code):
    raise ClassificationWriteError(code)


def _uuid(value, code):
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = UUID(value)
    except ValueError:
        _fail(code)
    if str(parsed) != value:
        _fail(code)
    return parsed


def _accepts_json(value):
    if value is None:
        return True
    # Honor the most specific matching range, including an explicit JSON q=0.
    matches = []
    for item in parse_http_list(value):
        parts = [part.strip().lower() for part in item.split(";")]
        specificity = {"*/*": 0, "application/*": 1, "application/json": 2}.get(parts[0])
        # Only ranges matching our unparameterized JSON representation count.
        # Quoted commas in unrelated parameters cannot invent another range.
        if specificity is None or any(parameter and not parameter.startswith("q=") for parameter in parts[1:]):
            continue
        quality = 1.0
        seen_q = False
        for parameter in parts[1:]:
            if (seen_q or re.fullmatch(r"q=(?:0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?)", parameter) is None):
                return False
            seen_q = True
            quality = float(parameter[2:])
        if specificity is not None:
            matches.append((specificity, quality))
    if not matches:
        return False
    specificity = max(level for level, _ in matches)
    return min(q for level, q in matches if level == specificity) > 0


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("request_body_invalid")
        result[key] = value
    return result


def _body(request):
    if not _accepts_json(request.META.get("HTTP_ACCEPT")):
        _fail("not_acceptable")
    if request.META.get("QUERY_STRING", ""):
        _fail("query_parameters_not_allowed")
    if (re.fullmatch(
        r'application/json(?:\s*;\s*charset=(?:utf-8|"utf-8"))?',
        request.META.get("CONTENT_TYPE", ""), re.IGNORECASE,
    ) is None or request.META.get("HTTP_CONTENT_ENCODING", "identity") != "identity"):
        _fail("unsupported_media_type")
    # Never use request.body or DRF's implicit parsers: even a forged declared
    # length cannot make this adapter read more than the limit plus one byte.
    raw = request.read(1025)
    if len(raw) > 1024:
        _fail("request_body_too_large")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object,
            parse_constant=lambda _: _fail("malformed_json"),
            # A decimal/exponent token is never a revision integer, even 0e0.
            parse_float=lambda _: _JSON_NON_INTEGER,
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ClassificationWriteError):
            raise
        _fail("malformed_json")
    if type(value) is not dict:
        _fail("request_body_invalid")
    return value


@method_decorator(csrf_exempt, name="dispatch")
class _ClassificationWriteView(View):
    """No ambient auth/CSRF state or automatic negotiation/HEAD/OPTIONS.

    The explicit Origin plus capability gate is the CSRF defense. A plain
    Django View keeps this ordered protocol independent of DRF's pre-dispatch
    negotiation and format overrides; existing DRF reads remain unchanged.
    """

    allowed_method = None

    def dispatch(self, request, *args, **kwargs):
        request.gouda_classification_write = True
        try:
            delivery = require_active_local_delivery_runtime()
            runtime = require_classification_write_runtime()
            try:
                host = request.get_host()
            except DisallowedHost:
                _fail("host_not_allowed")
            if "HTTP_HOST" not in request.META or host != WRITE_HOST:
                _fail("host_not_allowed")
            if request.method != self.allowed_method:
                _fail("method_not_allowed")
            if request.META.get("HTTP_ORIGIN") != WRITE_ORIGIN:
                _fail("origin_not_allowed")
            grant = None
            if self.allowed_method == "PATCH":
                grant = runtime.verify_capability(
                    request.META.get("HTTP_X_GOUDA_CLASSIFICATION_WRITE"),
                )
            principal = delivery.trusted_principal_context()
            validate_principal_context(principal)
            body = _body(request)
            payload = self.execute(body, principal, grant, runtime, **kwargs)
            response = JsonResponse(payload)
        except (LocalDeliveryBootstrapError, ClassificationWriteError,
                AccountAccessServiceError, MovementClassificationServiceError) as error:
            code = error.code if error.code in _ERROR_STATUS else "internal_error"
            response = JsonResponse({"code": code}, status=_ERROR_STATUS[code])
        except Exception:
            # No exception message/trace/locals, submitted data, or secret.
            _logger.error("classification internal_error")
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


class ClassificationWriteCapabilityView(_ClassificationWriteView):
    allowed_method = "POST"

    def execute(self, body, principal, grant, runtime):
        if body != {}:
            _fail("request_body_invalid")
        return {"write_capability": runtime.bootstrap_capability()}


class MovementClassificationView(_ClassificationWriteView):
    allowed_method = "PATCH"

    def execute(self, body, principal, grant, runtime, account_uuid, movement_uuid):
        if set(body) != {"category_id", "expected_revision"}:
            _fail("request_body_invalid")
        account_id = _uuid(account_uuid, "account_selector_invalid")
        movement_id = _uuid(movement_uuid, "movement_id_invalid")
        category_id = body["category_id"]
        if category_id is not None:
            category_id = _uuid(category_id, "category_id_invalid")
        revision = body["expected_revision"]
        if type(revision) is not int or not 0 <= revision <= 2**63 - 1:
            _fail("expected_revision_invalid")
        classification = classify_authorized_movement(
            principal_context=principal, write_grant=grant,
            account_selector=account_id, movement_id=movement_id,
            category_id=category_id, expected_revision=revision,
        )
        return {"classification": _serialize_classification(classification)}
