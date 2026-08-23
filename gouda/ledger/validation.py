"""Small explicit validators for persistence-domain values."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError


MONEY_MAX_DIGITS = 20
MONEY_DECIMAL_PLACES = 2
MONEY_MAX_WHOLE_DIGITS = MONEY_MAX_DIGITS - MONEY_DECIMAL_PLACES


def validate_exact_money(value: Decimal, *, field_name: str = "value") -> None:
    """Reject a Decimal that PostgreSQL numeric(20,2) cannot store exactly.

    This validator deliberately never quantizes or otherwise changes ``value``.
    The future import service must call it before creating financial records.
    """

    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError(
            f"{field_name} must be a finite Decimal.",
            code="money_not_finite",
        )

    sign, digits, exponent = value.as_tuple()
    decimal_places = max(0, -exponent)
    digit_count = len(digits)
    if exponent >= 0:
        digit_count += exponent
    digit_count = max(digit_count, decimal_places)
    whole_digits = digit_count - decimal_places

    if decimal_places > MONEY_DECIMAL_PLACES:
        raise ValidationError(
            f"{field_name} requires more than {MONEY_DECIMAL_PLACES} decimal places.",
            code="money_scale_exceeded",
        )
    if digit_count > MONEY_MAX_DIGITS or whole_digits > MONEY_MAX_WHOLE_DIGITS:
        raise ValidationError(
            f"{field_name} exceeds the {MONEY_MAX_DIGITS}-digit money domain.",
            code="money_precision_exceeded",
        )
