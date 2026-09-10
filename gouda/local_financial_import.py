"""Process-local authority for the one supported private financial import."""

from contextlib import contextmanager
import re
import secrets
import threading

from django.conf import settings

from gouda.local_delivery import (
    LocalDeliveryBootstrapError,
    require_active_local_delivery_runtime,
)


IMPORT_ORIGIN = "http://127.0.0.1:5173"
IMPORT_HOST = "127.0.0.1:5173"
PRIVATE_DATABASE_NAME = "gouda_private"
_ISSUER = object()
_active_runtime = None


class FinancialImportError(ValueError):
    """A safe failure at the local financial-import authority boundary."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class SantanderCurrentAccountImportGrant:
    """Opaque authority for only Santander current-account XLSX import."""

    __slots__ = ()

    def __repr__(self):
        return "SantanderCurrentAccountImportGrant(<opaque>)"


class LocalFinancialImportRuntime:
    __slots__ = ("_delivery", "_capability", "_grant", "_upload_slot")

    def __init__(self, delivery, *, issuer):
        if issuer is not _ISSUER:
            raise TypeError("Financial import runtime requires validated startup")
        self._delivery = delivery
        self._capability = secrets.token_hex(32)
        self._grant = SantanderCurrentAccountImportGrant()
        self._upload_slot = threading.Lock()

    def _require_live(self):
        if (
            self is not _active_runtime
            or self._delivery is not require_active_local_delivery_runtime()
        ):
            raise FinancialImportError("import_capability_invalid")

    def bootstrap_capability(self):
        self._require_live()
        return self._capability

    def verify_capability(self, value):
        self._require_live()
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
            or not secrets.compare_digest(value, self._capability)
        ):
            raise FinancialImportError("import_capability_invalid")
        return self._grant

    @contextmanager
    def acquire_upload_slot(self):
        self._require_live()
        if not self._upload_slot.acquire(blocking=False):
            raise FinancialImportError("import_busy")
        try:
            self._require_live()
            yield
        finally:
            self._upload_slot.release()

    def __repr__(self):
        return "LocalFinancialImportRuntime(<opaque>)"


def validate_financial_import_startup(delivery, *, enabled, origin):
    """Validate protected launch options before generating any secret."""

    if type(enabled) is not bool:
        raise LocalDeliveryBootstrapError("financial_import_mode_invalid")
    if not enabled:
        if origin is not None:
            raise LocalDeliveryBootstrapError("financial_import_mode_invalid")
        return
    if origin != IMPORT_ORIGIN:
        raise LocalDeliveryBootstrapError("financial_import_origin_invalid")
    if delivery.bind_host not in {"127.0.0.1", "0.0.0.0"} or delivery.port != 8000:
        raise LocalDeliveryBootstrapError("financial_import_topology_invalid")
    if settings.DEBUG:
        raise LocalDeliveryBootstrapError("financial_import_debug_forbidden")
    if settings.DATABASES["default"]["NAME"] != PRIVATE_DATABASE_NAME:
        raise LocalDeliveryBootstrapError("financial_import_dataset_invalid")


@contextmanager
def _activate_validated_financial_imports(delivery, *, enabled, origin):
    validate_financial_import_startup(delivery, enabled=enabled, origin=origin)
    global _active_runtime
    if _active_runtime is not None:
        raise LocalDeliveryBootstrapError("financial_import_already_active")
    if require_active_local_delivery_runtime() is not delivery:
        raise LocalDeliveryBootstrapError("local_delivery_not_active")
    runtime = LocalFinancialImportRuntime(delivery, issuer=_ISSUER) if enabled else None
    _active_runtime = runtime
    try:
        yield
    finally:
        _active_runtime = None
        if runtime is not None:
            runtime._capability = None
            runtime._grant = None


def require_financial_import_runtime():
    require_active_local_delivery_runtime()
    if _active_runtime is None:
        raise FinancialImportError("financial_import_not_enabled")
    _active_runtime._require_live()
    return _active_runtime


def validate_santander_current_account_import_grant(grant):
    runtime = require_financial_import_runtime()
    if grant is not runtime._grant:
        raise FinancialImportError("import_capability_invalid")
