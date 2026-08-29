"""Strict JSON provenance validation for BCI Historical evidence."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .extraction import BoundingBox
from .types import FieldProvenance


PROVENANCE_SCHEMA_VERSION = "bci-historical-field-provenance-v1"


class BciHistoricalProvenanceError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def serialize_field_provenance_map(fields: Mapping[str, FieldProvenance]) -> dict[str, object]:
    if not isinstance(fields, Mapping):
        raise BciHistoricalProvenanceError("provenance_fields_invalid")
    result = {"schema": PROVENANCE_SCHEMA_VERSION, "fields": {}}
    for name in sorted(fields):
        if not isinstance(name, str) or not name or "\x00" in name:
            raise BciHistoricalProvenanceError("provenance_field_name_invalid")
        result["fields"][name] = _serialize(fields[name])  # type: ignore[index]
    return validate_field_provenance_payload(result)


def validate_field_provenance_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != {"schema", "fields"} or payload.get("schema") != PROVENANCE_SCHEMA_VERSION:
        raise BciHistoricalProvenanceError("provenance_payload_invalid")
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise BciHistoricalProvenanceError("provenance_fields_invalid")
    return {"schema": PROVENANCE_SCHEMA_VERSION, "fields": {name: _validate(item) for name, item in sorted(fields.items())}}


def validate_positive_ordinal_list(value: object, *, allow_empty: bool = False) -> list[int]:
    if not isinstance(value, list) or (not value and not allow_empty) or any(type(item) is not int or item <= 0 for item in value) or len(set(value)) != len(value):
        raise BciHistoricalProvenanceError("provenance_ordinals_invalid")
    return list(value)


def _serialize(value: FieldProvenance) -> dict[str, object]:
    if not isinstance(value, FieldProvenance):
        raise BciHistoricalProvenanceError("provenance_field_invalid")
    return {
        "role": value.role,
        "band_relation": value.band_relation,
        "page_ordinal": value.page_ordinal,
        "line_ordinals": list(value.line_ordinals),
        "token_ordinals": list(value.token_ordinals),
        "bbox": [format(getattr(value.bbox, name), "f") for name in ("x0", "y0", "x1", "y1")],
        "page_width": format(value.page_width, "f"),
        "page_height": format(value.page_height, "f"),
        "normalized_bbox": [format(item, "f") for item in value.normalized_bbox],
    }


def _validate(value: object) -> dict[str, object]:
    required = {"role", "band_relation", "page_ordinal", "line_ordinals", "token_ordinals", "bbox", "page_width", "page_height", "normalized_bbox"}
    if not isinstance(value, dict) or set(value) != required:
        raise BciHistoricalProvenanceError("provenance_field_invalid")
    if not isinstance(value["role"], str) or not value["role"] or not isinstance(value["band_relation"], str) or not value["band_relation"]:
        raise BciHistoricalProvenanceError("provenance_text_invalid")
    page = value["page_ordinal"]
    if type(page) is not int or page <= 0:
        raise BciHistoricalProvenanceError("provenance_ordinal_invalid")
    lines = validate_positive_ordinal_list(value["line_ordinals"])
    tokens = validate_positive_ordinal_list(value["token_ordinals"])
    bbox = _box(value["bbox"], "provenance_bbox_invalid")
    width = _decimal(value["page_width"], positive=True)
    height = _decimal(value["page_height"], positive=True)
    normalized = _box(value["normalized_bbox"], "provenance_normalized_bbox_invalid", maximum=Decimal("1"))
    if bbox[2] > width or bbox[3] > height:
        raise BciHistoricalProvenanceError("provenance_bbox_invalid")
    return {"role": value["role"], "band_relation": value["band_relation"], "page_ordinal": page, "line_ordinals": lines, "token_ordinals": tokens, "bbox": [format(item, "f") for item in bbox], "page_width": format(width, "f"), "page_height": format(height, "f"), "normalized_bbox": [format(item, "f") for item in normalized]}


def _box(value: object, code: str, maximum: Decimal | None = None) -> list[Decimal]:
    if not isinstance(value, list) or len(value) != 4:
        raise BciHistoricalProvenanceError(code)
    values = [_decimal(item) for item in value]
    if any(item < 0 or (maximum is not None and item > maximum) for item in values) or values[0] > values[2] or values[1] > values[3]:
        raise BciHistoricalProvenanceError(code)
    return values


def _decimal(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise BciHistoricalProvenanceError("provenance_decimal_invalid")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise BciHistoricalProvenanceError("provenance_decimal_invalid") from None
    if not result.is_finite() or format(result, "f") != value or (positive and result <= 0):
        raise BciHistoricalProvenanceError("provenance_decimal_invalid")
    return result
