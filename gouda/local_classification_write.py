"""Process-local, classification-only authority issued by validated startup."""

from contextlib import contextmanager
import re
import secrets

from django.conf import settings

from gouda.local_delivery import (
    LocalDeliveryBootstrapError,
    require_active_local_delivery_runtime,
)


WRITE_ORIGIN = "http://127.0.0.1:5173"
WRITE_HOST = "127.0.0.1:5173"
_ISSUER = object()
_active_runtime = None


class ClassificationWriteError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ClassificationWriteGrant:
    """Only the live runtime's singleton grant is accepted."""

    __slots__ = ()

    def __repr__(self):
        return "ClassificationWriteGrant(<opaque>)"


class LocalClassificationWriteRuntime:
    __slots__ = ("_delivery", "_capability", "_grant")

    def __init__(self, delivery, *, issuer):
        if issuer is not _ISSUER:
            raise TypeError("Classification runtime requires validated startup")
        self._delivery = delivery
        self._capability = secrets.token_hex(32)
        self._grant = ClassificationWriteGrant()

    def _require_live(self):
        if (self is not _active_runtime
                or self._delivery is not require_active_local_delivery_runtime()):
            raise ClassificationWriteError("write_capability_invalid")

    def bootstrap_capability(self):
        """Delivery calls this only after the complete bootstrap request gate."""
        self._require_live()
        return self._capability

    def verify_capability(self, value):
        self._require_live()
        if (not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
                or not secrets.compare_digest(value, self._capability)):
            raise ClassificationWriteError("write_capability_invalid")
        return self._grant

    def __repr__(self):
        return "LocalClassificationWriteRuntime(<opaque>)"


def validate_write_startup(delivery, *, enabled, origin):
    """Protected launch options only; no environment-configured secret."""
    if type(enabled) is not bool:
        raise LocalDeliveryBootstrapError("classification_write_mode_invalid")
    if not enabled:
        if origin is not None:
            raise LocalDeliveryBootstrapError("classification_write_mode_invalid")
        return
    if origin != WRITE_ORIGIN:
        raise LocalDeliveryBootstrapError("classification_write_origin_invalid")
    if delivery.bind_host not in {"127.0.0.1", "0.0.0.0"} or delivery.port != 8000:
        raise LocalDeliveryBootstrapError("classification_write_topology_invalid")
    if settings.DEBUG:
        raise LocalDeliveryBootstrapError("classification_write_debug_forbidden")


@contextmanager
def _activate_validated_classification_writes(delivery, *, enabled, origin):
    validate_write_startup(delivery, enabled=enabled, origin=origin)
    global _active_runtime
    if _active_runtime is not None:
        raise LocalDeliveryBootstrapError("classification_write_already_active")
    if require_active_local_delivery_runtime() is not delivery:
        raise LocalDeliveryBootstrapError("local_delivery_not_active")
    runtime = LocalClassificationWriteRuntime(delivery, issuer=_ISSUER) if enabled else None
    _active_runtime = runtime
    try:
        yield
    finally:
        _active_runtime = None
        if runtime is not None:
            runtime._capability = None
            runtime._grant = None


def require_classification_write_runtime():
    require_active_local_delivery_runtime()
    if _active_runtime is None:
        raise ClassificationWriteError("mutation_not_enabled")
    _active_runtime._require_live()
    return _active_runtime


def validate_classification_write_grant(grant):
    runtime = require_classification_write_runtime()
    if grant is not runtime._grant:
        raise ClassificationWriteError("write_capability_invalid")
