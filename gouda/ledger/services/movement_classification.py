"""Trusted internal manual classification; no HTTP write authorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from ..models import Account, Category, Movement, MovementClassification


class MovementClassificationServiceError(ValueError):
    """A deterministic classification failure with a stable, safe code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MovementClassificationState:
    movement_id: UUID
    category_id: UUID | None
    source: str | None
    revision: int
    updated_at: datetime | None


def set_movement_classification(
    *,
    account: Account,
    movement_id: UUID,
    category_id: UUID | None,
    expected_revision: int,
) -> MovementClassificationState:
    """Assign/change/clear one persisted Movement scoped to a trusted Account.

    Revision 0 denotes no row. Correct-revision repeats are no-ops, including
    clearing an absent row. Account -> Movement -> Category locks serialize
    first writes, corrections and target retirement in one transaction. An
    enclosing transaction may roll back the result; locks last until commit.
    Category provisioning/retirement is trusted model work, not this command.
    """

    if (
        not isinstance(account, Account)
        or account._state.adding
        or not isinstance(account.pk, UUID)
        or account._state.db != "default"
    ):
        _fail("account_not_persisted")
    if not isinstance(movement_id, UUID):
        _fail("movement_id_invalid")
    if category_id is not None and not isinstance(category_id, UUID):
        _fail("category_id_invalid")
    if type(expected_revision) is not int or not 0 <= expected_revision <= 2**63 - 1:
        _fail("expected_revision_invalid")

    with transaction.atomic():
        if not Account.objects.select_for_update().filter(pk=account.pk).first():
            _fail("account_not_found")
        movement = Movement.objects.select_for_update().filter(
            pk=movement_id, account_id=account.pk
        ).first()
        if movement is None:
            _fail("movement_not_found")
        current = MovementClassification.objects.filter(movement=movement).first()
        if current is None and expected_revision != 0:
            _fail("classification_not_present")
        if current is not None and current.revision != expected_revision:
            _fail("classification_revision_conflict")

        category = None
        if category_id is not None:
            category = Category.objects.select_for_update().filter(pk=category_id).first()
            if category is None:
                _fail("category_not_found")

        current_category_id = current.category_id if current else None
        if current_category_id == category_id:
            return _state(movement_id, current)
        if category is not None and not category.is_active:
            _fail("category_inactive")
        if current is not None and current.revision == 2**63 - 1:
            _fail("classification_revision_exhausted")

        if current is None:
            current = MovementClassification(movement=movement)
        else:
            current.revision += 1
        current.category = category
        current.source = MovementClassification.Source.MANUAL
        current.updated_at = timezone.now()
        current.save()
        return _state(movement_id, current)


def _state(movement_id, current):
    return MovementClassificationState(
        movement_id=movement_id,
        category_id=current.category_id if current else None,
        source=current.source if current else None,
        revision=current.revision if current else 0,
        updated_at=current.updated_at if current else None,
    )


def _fail(code):
    raise MovementClassificationServiceError(code)
