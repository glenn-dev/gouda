"""Narrow local-MVP HTTP delivery for canonical Movement reporting."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from uuid import UUID

from rest_framework.exceptions import NotAcceptable
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from gouda.local_delivery import (
    LocalDeliveryBootstrapError,
    require_active_local_delivery_runtime,
)

from .services.account_access import (
    AccountAccessServiceError,
    report_authorized_canonical_movements,
)
from .services.movement_reporting import (
    MovementReport,
    MovementReportItem,
    MovementReportingServiceError,
    MovementSourceTrace,
)


_ISO_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

_ERROR_STATUS = {
    "local_delivery_not_active": 503,
    "principal_context_invalid": 403,
    "account_selector_invalid": 400,
    "account_not_accessible": 404,
    "start_date_invalid": 400,
    "end_date_invalid": 400,
    "date_range_invalid": 400,
    "not_acceptable": 406,
}


class CanonicalMovementReportView(APIView):
    """Deliver one authorized canonical Movement report as explicit JSON."""

    authentication_classes = ()
    permission_classes = ()
    parser_classes = ()
    renderer_classes = (JSONRenderer,)
    http_method_names = ("get",)

    def get(self, request: Request, account_uuid: str) -> Response:
        try:
            runtime = require_active_local_delivery_runtime()
            principal_context = runtime.trusted_principal_context()
        except LocalDeliveryBootstrapError:
            return _error_response("local_delivery_not_active")

        try:
            account_selector = _parse_account_uuid(account_uuid)
            start_date = _required_query_date(request, "start_date")
            end_date = _required_query_date(request, "end_date")
            report = report_authorized_canonical_movements(
                principal_context=principal_context,
                account_selector=account_selector,
                start_date=start_date,
                end_date=end_date,
            )
        except AccountAccessServiceError as error:
            return _error_response(error.code)
        except MovementReportingServiceError as error:
            return _error_response(error.code)

        return Response(_serialize_report(report), status=200)

    def http_method_not_allowed(self, request: Request, *args, **kwargs) -> Response:
        return Response({"code": "method_not_allowed"}, status=405)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, NotAcceptable):
            return _error_response("not_acceptable")
        return super().handle_exception(exc)


def _parse_account_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise AccountAccessServiceError("account_selector_invalid")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise AccountAccessServiceError("account_selector_invalid") from None
    if str(parsed) != value:
        raise AccountAccessServiceError("account_selector_invalid")
    return parsed


def _required_query_date(request: Request, name: str) -> date:
    values = request.query_params.getlist(name)
    code = f"{name}_invalid"
    if len(values) != 1 or _ISO_DATE.fullmatch(values[0]) is None:
        raise MovementReportingServiceError(code)
    try:
        return date.fromisoformat(values[0])
    except ValueError:
        raise MovementReportingServiceError(code) from None


def _serialize_report(report: MovementReport) -> dict[str, object]:
    return {
        "account_id": str(report.account_id),
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "movement_count": report.movement_count,
        "net_signed_amount": _decimal_string(report.net_signed_amount),
        "movements": [_serialize_movement(item) for item in report.movements],
    }


def _serialize_movement(item: MovementReportItem) -> dict[str, object]:
    return {
        "movement_id": str(item.movement_id),
        "account_id": str(item.account_id),
        "occurrence_date": item.occurrence_date.isoformat(),
        "signed_amount": _decimal_string(item.signed_amount),
        "currency": item.currency,
        "description": item.description,
        "source_trace": _serialize_source_trace(item.source_trace),
    }


def _serialize_source_trace(trace: MovementSourceTrace) -> dict[str, object]:
    return {
        "raw_record_id": str(trace.raw_record_id),
        "import_batch_id": str(trace.import_batch_id),
        "source_artifact_id": str(trace.source_artifact_id),
        "source_kind": trace.source_kind,
        "source_variant": trace.source_variant,
        "parser_version": trace.parser_version,
        "import_status": trace.import_status,
        "reconciliation_status": trace.reconciliation_status,
    }


def _decimal_string(value: Decimal) -> str:
    return format(value, "f")


def _error_response(code: str) -> Response:
    status = _ERROR_STATUS.get(code, 500)
    safe_code = code if code in _ERROR_STATUS else "internal_error"
    return Response({"code": safe_code}, status=status)
