"""Fail-closed bootstrap for unauthenticated loopback-only delivery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, TypeVar

if TYPE_CHECKING:
    from gouda.ledger.services.account_access import TrustedPrincipalContext


_ALLOWED_BIND_HOSTS = frozenset({"127.0.0.1", "::1"})
_TRUSTED_CONTAINER_BIND_HOST = "0.0.0.0"
_TRUSTED_CONTAINER_PORT = 8000
_RUNTIME_ISSUER = object()
_RunnerResult = TypeVar("_RunnerResult")


class LocalDeliveryBootstrapError(ValueError):
    """A deterministic local-delivery bootstrap failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LocalDeliveryRuntime:
    """Opaque proof of the active validated local-delivery bootstrap.

    The value is process-local and carries only the validated server bind. It
    is deliberately not a user, ownership record, or durable credential.
    Python imports are not a security boundary; trusted composition must still
    use the supported launcher rather than constructing or bypassing internals.
    """

    __slots__ = ("_bind_host", "_port", "_trusted_container_network")

    def __init__(
        self,
        *,
        bind_host: str,
        port: int,
        trusted_container_network: bool,
        issuer: object,
    ):
        if issuer is not _RUNTIME_ISSUER:
            raise TypeError("LocalDeliveryRuntime is issued by Gouda bootstrap only")
        self._bind_host = bind_host
        self._port = port
        self._trusted_container_network = trusted_container_network

    @property
    def bind_host(self) -> str:
        return self._bind_host

    @property
    def port(self) -> int:
        return self._port

    @property
    def django_addrport(self) -> str:
        if self._bind_host == "::1":
            return f"[::1]:{self._port}"
        return f"{self._bind_host}:{self._port}"

    @property
    def uses_ipv6(self) -> bool:
        return self._bind_host == "::1"

    @property
    def uses_trusted_container_network(self) -> bool:
        return self._trusted_container_network

    def trusted_principal_context(self) -> TrustedPrincipalContext:
        """Issue the temporary principal only while this runtime is active."""

        if self is not _active_runtime:
            raise LocalDeliveryBootstrapError("local_delivery_not_active")

        from gouda.ledger.services.account_access import (
            trusted_local_principal_context,
        )

        return trusted_local_principal_context()

    def __repr__(self) -> str:
        return "LocalDeliveryRuntime(<opaque>)"


_active_runtime: LocalDeliveryRuntime | None = None


def run_validated_local_delivery(
    *,
    bind_host: object,
    port: object,
    trusted_container_network: object = False,
    server_runner: Callable[[LocalDeliveryRuntime], _RunnerResult],
) -> _RunnerResult:
    """Validate, activate, and invoke the controlled server runner.

    ``bind_host`` and ``port`` are trusted launch configuration, never request
    values. The dedicated launcher passes only the issued runtime's derived
    bind to Django. Capability activation and server delegation are therefore
    one supported composition operation rather than independent mode and bind
    claims. Container mode validates only the internal bind and explicit mode;
    it does not inspect Docker publication or network membership. The
    repository-owned Compose configuration owns that external guarantee.
    """

    runtime = _build_runtime(
        bind_host=bind_host,
        port=port,
        trusted_container_network=trusted_container_network,
    )

    global _active_runtime
    if _active_runtime is not None:
        raise LocalDeliveryBootstrapError("local_delivery_already_active")

    _active_runtime = runtime
    try:
        return server_runner(runtime)
    finally:
        if _active_runtime is runtime:
            _active_runtime = None


def require_active_local_delivery_runtime() -> LocalDeliveryRuntime:
    """Return the active bootstrap capability or fail closed."""

    if _active_runtime is None:
        raise LocalDeliveryBootstrapError("local_delivery_not_active")
    return _active_runtime


def _build_runtime(
    *,
    bind_host: object,
    port: object,
    trusted_container_network: object,
) -> LocalDeliveryRuntime:
    if not isinstance(trusted_container_network, bool):
        raise LocalDeliveryBootstrapError("container_network_mode_invalid")

    expected_hosts = (
        frozenset({_TRUSTED_CONTAINER_BIND_HOST})
        if trusted_container_network
        else _ALLOWED_BIND_HOSTS
    )
    if not isinstance(bind_host, str) or bind_host not in expected_hosts:
        raise LocalDeliveryBootstrapError("bind_host_invalid")

    if (
        not isinstance(port, str)
        or not port.isascii()
        or not port.isdecimal()
        or len(port) > 5
        or port.startswith("0")
    ):
        raise LocalDeliveryBootstrapError("port_invalid")

    parsed_port = int(port)
    if parsed_port < 1 or parsed_port > 65535:
        raise LocalDeliveryBootstrapError("port_invalid")
    if trusted_container_network and parsed_port != _TRUSTED_CONTAINER_PORT:
        raise LocalDeliveryBootstrapError("port_invalid")

    return LocalDeliveryRuntime(
        bind_host=bind_host,
        port=parsed_port,
        trusted_container_network=trusted_container_network,
        issuer=_RUNTIME_ISSUER,
    )
