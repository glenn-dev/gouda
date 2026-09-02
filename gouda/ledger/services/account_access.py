"""Trusted Account-read discovery, resolution, and Movement reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ..models import Account
from . import movement_reporting
from .movement_reporting import MovementReport


class AccountAccessServiceError(ValueError):
    """A deterministic Account-access failure with a stable safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class TrustedPrincipalContext:
    """Opaque caller context issued by trusted application composition.

    This value carries no personal, ownership, Account, or provider data.  Its
    constructor is public only because Python modules cannot enforce a security
    boundary; the temporary policy recognizes solely the module-issued
    singleton returned by :func:`trusted_local_principal_context`.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "TrustedPrincipalContext(<opaque>)"


_TRUSTED_LOCAL_PRINCIPAL = TrustedPrincipalContext()


@dataclass(frozen=True)
class AccountSummary:
    """Minimal canonical Account fields approved for read discovery."""

    id: UUID
    display_name: str
    kind: str
    currency: str


def trusted_local_principal_context() -> TrustedPrincipalContext:
    """Return the temporary principal for trusted server-side composition.

    A future authentication or local bootstrap boundary may call this function
    after establishing caller trust.  Delivery code must never call it merely
    because a client supplied a matching string, header, selector, or artifact.
    """

    return _TRUSTED_LOCAL_PRINCIPAL


def list_read_accounts(*, principal_context: object) -> tuple[AccountSummary, ...]:
    """Return privacy-safe summaries for Accounts the principal may read.

    The temporary policy grants the recognized local principal read access to
    every persisted Account.  Authorization remains inside this service so a
    future policy can narrow visibility without making the HTTP adapter query
    the Account model directly.
    """

    _validate_principal_context(principal_context)
    accounts = Account.objects.only(
        "id",
        "display_name",
        "kind",
        "currency",
    ).order_by("display_name", "pk")
    return tuple(
        AccountSummary(
            id=account.pk,
            display_name=account.display_name,
            kind=account.kind,
            currency=account.currency,
        )
        for account in accounts
        if _principal_may_read_account(
            principal_context=principal_context,
            account_id=account.pk,
        )
    )


def resolve_read_account(
    *,
    principal_context: object,
    account_selector: object,
) -> Account:
    """Resolve one untrusted UUID to an Account authorized for reading.

    The temporary policy grants the one recognized local principal read access
    to every persisted Account.  This is authorization policy, not ownership.
    Unknown and policy-denied UUIDs intentionally share one safe failure.
    """

    _validate_principal_context(principal_context)
    account_id = _validate_account_selector(account_selector)

    if not _principal_may_read_account(
        principal_context=principal_context,
        account_id=account_id,
    ):
        raise AccountAccessServiceError("account_not_accessible")

    try:
        return Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        raise AccountAccessServiceError("account_not_accessible") from None


def report_authorized_canonical_movements(
    *,
    principal_context: object,
    account_selector: object,
    start_date: date,
    end_date: date,
) -> MovementReport:
    """Resolve Account read access, then delegate canonical reporting.

    Date validation, Movement selection, ordering, totals, and source-trace
    projection remain owned by ``report_canonical_movements``.  This operation
    is the intended application entry point for a future read-only delivery
    adapter; the lower-level reporting service still requires an already
    trusted persisted Account.
    """

    account = resolve_read_account(
        principal_context=principal_context,
        account_selector=account_selector,
    )
    try:
        return movement_reporting.report_canonical_movements(
            account=account,
            start_date=start_date,
            end_date=end_date,
        )
    except movement_reporting.MovementReportingServiceError as error:
        if error.code == "account_not_found":
            raise AccountAccessServiceError("account_not_accessible") from None
        raise


def _validate_principal_context(principal_context: object) -> None:
    if principal_context is not _TRUSTED_LOCAL_PRINCIPAL:
        raise AccountAccessServiceError("principal_context_invalid")


def _validate_account_selector(account_selector: object) -> UUID:
    if not isinstance(account_selector, UUID):
        raise AccountAccessServiceError("account_selector_invalid")
    return account_selector


def _principal_may_read_account(
    *,
    principal_context: object,
    account_id: UUID,
) -> bool:
    """Temporary policy seam; ``account_id`` is a selector, not ownership."""

    return (
        principal_context is _TRUSTED_LOCAL_PRINCIPAL
        and isinstance(account_id, UUID)
    )
