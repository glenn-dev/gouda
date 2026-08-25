"""Strict JSON projection for Santander TDC PDF field provenance v1."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .types import AdditionalPageSpan, FieldProvenance


PROVENANCE_SCHEMA_VERSION = "santander-tdc-field-provenance-v1"
_PROVENANCE_KEYS = {
    "role",
    "band_relation",
    "page_ordinal",
    "line_ordinals",
    "token_ordinals",
    "bbox",
    "page_width",
    "page_height",
    "normalized_bbox",
    "additional_page_spans",
}
_SPAN_KEYS = {
    "page_ordinal",
    "line_ordinals",
    "token_ordinals",
    "bbox",
    "page_width",
    "page_height",
    "normalized_bbox",
}


class SantanderTdcProvenanceError(ValueError):
    """Safe validation failure for the frozen provenance JSON shape."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def serialize_field_provenance_map(
    fields: Mapping[str, FieldProvenance],
) -> dict[str, object]:
    """Serialize an immutable parser mapping without introducing JSON floats."""

    if not isinstance(fields, Mapping):
        raise SantanderTdcProvenanceError("provenance_fields_invalid")
    serialized: dict[str, object] = {
        "schema": PROVENANCE_SCHEMA_VERSION,
        "fields": {
            name: _serialize_provenance(value)
            for name, value in sorted(fields.items())
            if _validate_field_name(name)
        },
    }
    return validate_field_provenance_payload(serialized)


def validate_field_provenance_payload(payload: object) -> dict[str, object]:
    """Return a defensive normalized copy of a strict v1 provenance payload."""

    if not isinstance(payload, dict) or set(payload) != {"schema", "fields"}:
        raise SantanderTdcProvenanceError("provenance_payload_invalid")
    if payload.get("schema") != PROVENANCE_SCHEMA_VERSION:
        raise SantanderTdcProvenanceError("provenance_schema_unsupported")
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise SantanderTdcProvenanceError("provenance_fields_invalid")
    normalized_fields: dict[str, object] = {}
    for name in sorted(fields):
        _validate_field_name(name)
        normalized_fields[name] = _validate_provenance(fields[name])
    return {"schema": PROVENANCE_SCHEMA_VERSION, "fields": normalized_fields}


def validate_positive_ordinal_list(value: object, *, allow_empty: bool = False) -> list[int]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise SantanderTdcProvenanceError("provenance_ordinals_invalid")
    if any(type(item) is not int or item <= 0 for item in value):
        raise SantanderTdcProvenanceError("provenance_ordinals_invalid")
    if len(set(value)) != len(value):
        raise SantanderTdcProvenanceError("provenance_ordinals_invalid")
    return list(value)


def _validate_field_name(value: object) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SantanderTdcProvenanceError("provenance_field_name_invalid")
    return True


def _serialize_provenance(value: FieldProvenance) -> dict[str, object]:
    if not isinstance(value, FieldProvenance):
        raise SantanderTdcProvenanceError("provenance_field_invalid")
    result = _serialize_span(value)
    result.update(
        role=_required_text(value.role),
        band_relation=_required_text(value.band_relation),
        additional_page_spans=[_serialize_span(span) for span in value.additional_page_spans],
    )
    return result


def _serialize_span(value: FieldProvenance | AdditionalPageSpan) -> dict[str, object]:
    return {
        "page_ordinal": _positive_int(value.page_ordinal),
        "line_ordinals": [_positive_int(item) for item in value.line_ordinals],
        "token_ordinals": [_positive_int(item) for item in value.token_ordinals],
        "bbox": _decimal_box(value.bbox),
        "page_width": _decimal_text(value.page_width, positive=True),
        "page_height": _decimal_text(value.page_height, positive=True),
        "normalized_bbox": _normalized_box(value.normalized_bbox),
    }


def _validate_provenance(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _PROVENANCE_KEYS:
        raise SantanderTdcProvenanceError("provenance_field_invalid")
    normalized = _validate_span(value, expected_keys=_PROVENANCE_KEYS)
    normalized["role"] = _required_text(value["role"])
    normalized["band_relation"] = _required_text(value["band_relation"])
    additional = value["additional_page_spans"]
    if not isinstance(additional, list):
        raise SantanderTdcProvenanceError("provenance_spans_invalid")
    normalized_additional = [
        _validate_span(span, expected_keys=_SPAN_KEYS)
        for span in additional
    ]
    pages = [normalized["page_ordinal"], *(span["page_ordinal"] for span in normalized_additional)]
    if len(set(pages)) != len(pages):
        raise SantanderTdcProvenanceError("provenance_spans_invalid")
    normalized["additional_page_spans"] = normalized_additional
    return normalized


def _validate_span(value: object, *, expected_keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise SantanderTdcProvenanceError("provenance_span_invalid")
    page_ordinal = _positive_int(value["page_ordinal"])
    line_ordinals = validate_positive_ordinal_list(value["line_ordinals"])
    token_ordinals = validate_positive_ordinal_list(value["token_ordinals"])
    bbox = _validate_decimal_box(value["bbox"])
    page_width = _validate_decimal_text(value["page_width"], positive=True)
    page_height = _validate_decimal_text(value["page_height"], positive=True)
    normalized_bbox = _validate_normalized_box(value["normalized_bbox"])
    if bbox[2] > page_width or bbox[3] > page_height:
        raise SantanderTdcProvenanceError("provenance_bbox_invalid")
    return {
        "page_ordinal": page_ordinal,
        "line_ordinals": line_ordinals,
        "token_ordinals": token_ordinals,
        "bbox": [format(item, "f") for item in bbox],
        "page_width": format(page_width, "f"),
        "page_height": format(page_height, "f"),
        "normalized_bbox": [format(item, "f") for item in normalized_bbox],
    }


def _decimal_box(value: object) -> list[str]:
    coordinates = _box_members(value)
    return [format(_decimal(item), "f") for item in coordinates]


def _normalized_box(value: object) -> list[str]:
    if not isinstance(value, tuple) or len(value) != 4:
        raise SantanderTdcProvenanceError("provenance_normalized_bbox_invalid")
    coordinates = [_decimal(item) for item in value]
    if any(item < 0 or item > 1 for item in coordinates):
        raise SantanderTdcProvenanceError("provenance_normalized_bbox_invalid")
    _validate_box_order(coordinates)
    return [format(item, "f") for item in coordinates]


def _validate_decimal_box(value: object) -> list[Decimal]:
    if not isinstance(value, list) or len(value) != 4:
        raise SantanderTdcProvenanceError("provenance_bbox_invalid")
    coordinates = [_validate_decimal_text(item) for item in value]
    if any(item < 0 for item in coordinates):
        raise SantanderTdcProvenanceError("provenance_bbox_invalid")
    _validate_box_order(coordinates)
    return coordinates


def _validate_normalized_box(value: object) -> list[Decimal]:
    if not isinstance(value, list) or len(value) != 4:
        raise SantanderTdcProvenanceError("provenance_normalized_bbox_invalid")
    coordinates = [_validate_decimal_text(item) for item in value]
    if any(item < 0 or item > 1 for item in coordinates):
        raise SantanderTdcProvenanceError("provenance_normalized_bbox_invalid")
    _validate_box_order(coordinates)
    return coordinates


def _validate_box_order(coordinates: list[Decimal]) -> None:
    if coordinates[0] > coordinates[2] or coordinates[1] > coordinates[3]:
        raise SantanderTdcProvenanceError("provenance_bbox_invalid")


def _box_members(value: object) -> tuple[object, object, object, object]:
    try:
        return (value.x0, value.y0, value.x1, value.y1)
    except AttributeError:
        raise SantanderTdcProvenanceError("provenance_bbox_invalid") from None


def _decimal_text(value: object, *, positive: bool = False) -> str:
    decimal = _decimal(value)
    if positive and decimal <= 0:
        raise SantanderTdcProvenanceError("provenance_dimension_invalid")
    return format(decimal, "f")


def _validate_decimal_text(value: object, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise SantanderTdcProvenanceError("provenance_decimal_invalid")
    try:
        decimal = Decimal(value)
    except InvalidOperation:
        raise SantanderTdcProvenanceError("provenance_decimal_invalid") from None
    if not decimal.is_finite() or format(decimal, "f") != value:
        raise SantanderTdcProvenanceError("provenance_decimal_invalid")
    if positive and decimal <= 0:
        raise SantanderTdcProvenanceError("provenance_dimension_invalid")
    return decimal


def _decimal(value: object) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise SantanderTdcProvenanceError("provenance_decimal_invalid")
    return value


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise SantanderTdcProvenanceError("provenance_ordinal_invalid")
    return value


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SantanderTdcProvenanceError("provenance_text_invalid")
    return value
