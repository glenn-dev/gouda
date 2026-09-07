"""Separate local classification authorization and locked result materialization."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from gouda.local_classification_write import validate_classification_write_grant
from ..models import MovementClassification
from . import account_access, movement_classification, movement_reporting


def classify_authorized_movement(
    *, principal_context: object, write_grant: object, account_selector: UUID,
    movement_id: UUID, category_id: UUID | None, expected_revision: int,
) -> movement_reporting.MovementClassificationProjection:
    account_access.validate_principal_context(principal_context)
    validate_classification_write_grant(write_grant)
    with transaction.atomic():
        account = account_access.resolve_read_account(
            principal_context=principal_context, account_selector=account_selector,
        )
        try:
            movement_classification.set_movement_classification(
                account=account, movement_id=movement_id,
                category_id=category_id, expected_revision=expected_revision,
            )
        except movement_classification.MovementClassificationServiceError as error:
            if error.code == "account_not_found":
                raise account_access.AccountAccessServiceError("account_not_accessible") from None
            raise
        # Account/Movement/target Category locks from the command still belong
        # to this outer transaction. No full Movement/report reload is needed.
        current = MovementClassification.objects.select_related("category").only(
            "movement_id", "category_id", "revision", "category__id",
            "category__display_name", "category__is_active",
        ).filter(
            movement_id=movement_id,
        ).first()
        return movement_reporting.project_movement_classification(current)
