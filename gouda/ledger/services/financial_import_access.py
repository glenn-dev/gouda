"""Authorized orchestration for the single local browser financial import."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
import re
import warnings
from uuid import UUID

from gouda.local_financial_import import (
    validate_santander_current_account_import_grant,
)

from ..demo_data import DEMO_ACCOUNT_IDS
from ..models import Account, ImportBatch
from .account_access import resolve_read_account, validate_principal_context
from .santander_import import import_santander_current_account_xlsx


class FinancialImportAccessError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class AdmittedStatement:
    content: bytes
    original_filename: str

    def __repr__(self):
        return "AdmittedStatement(<private>)"


def import_authorized_santander_current_account_xlsx(
    *,
    principal_context: object,
    import_grant: object,
    account_selector: UUID,
    admitted_statement_loader: Callable[[], AdmittedStatement],
    upload_slot: Callable[[], AbstractContextManager],
) -> ImportBatch:
    """Resolve authority and Account compatibility before receiving the file."""

    validate_principal_context(principal_context)
    validate_santander_current_account_import_grant(import_grant)
    account = resolve_read_account(
        principal_context=principal_context,
        account_selector=account_selector,
    )
    _validate_source_account(account)

    with upload_slot():
        statement = admitted_statement_loader()
        if not isinstance(statement, AdmittedStatement):
            raise FinancialImportAccessError("request_body_invalid")
        validate_principal_context(principal_context)
        validate_santander_current_account_import_grant(import_grant)
        # Workbook libraries may warn with source-derived text. The browser
        # boundary exposes only stable result/error codes, so warnings are not
        # an operator channel for private statement content.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return import_santander_current_account_xlsx(
                content=statement.content,
                original_filename=statement.original_filename,
                account=account,
            )


def _validate_source_account(account: Account) -> None:
    if (
        account.pk in DEMO_ACCOUNT_IDS
        or account.kind != Account.Kind.CURRENT
        or account.economic_orientation != Account.EconomicOrientation.ASSET
        or not isinstance(account.currency, str)
        or re.fullmatch(r"[A-Z]{3}", account.currency) is None
    ):
        raise FinancialImportAccessError("account_source_incompatible")
