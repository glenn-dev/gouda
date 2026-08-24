"""Deterministic native-text extraction for Santander TDC PDF GIR v1.

This module deliberately stops at geometric extraction. It has no financial,
account, persistence, or parser-section knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata
from typing import BinaryIO

import pdfplumber


GIR_VERSION = "TDC-PDF-GIR-v1"
PROFILE_VERSION = "santander-tdc-pdf-profile-v1"
_QUANTUM = Decimal("0.01")
_LETTER = (Decimal("612.00"), Decimal("792.00"))


class ConformanceCode(str, Enum):
    INVALID_PDF = "invalid_pdf"
    ENCRYPTED_PDF = "encrypted_pdf"
    PAGE_ACCESS_FAILED = "page_access_failed"
    NATIVE_TEXT_UNAVAILABLE = "native_text_unavailable"
    UNSUPPORTED_PAGE_GEOMETRY = "unsupported_page_geometry"


class ExtractionError(Exception):
    """Safe extraction/conformance error; it never includes source contents."""

    def __init__(self, code: ConformanceCode):
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, order=True)
class BoundingBox:
    x0: Decimal
    y0: Decimal
    x1: Decimal
    y1: Decimal

    def __post_init__(self) -> None:
        for name in ("x0", "y0", "x1", "y1"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                value = Decimal(str(value))
            object.__setattr__(self, name, value.quantize(_QUANTUM, rounding=ROUND_HALF_UP))

    def as_list(self) -> list[str]:
        return [str(value) for value in (self.x0, self.y0, self.x1, self.y1)]

    @classmethod
    def from_pdf_word(cls, word: dict, width: Decimal, height: Decimal) -> "BoundingBox":
        values = [Decimal(str(word[key])) for key in ("x0", "top", "x1", "bottom")]
        values = [max(Decimal("0"), min(value, limit)) for value, limit in zip(values, (width, height, width, height))]
        q = [value.quantize(_QUANTUM, rounding=ROUND_HALF_UP) for value in values]
        return cls(*q)

    @classmethod
    def union(cls, boxes: tuple["BoundingBox", ...]) -> "BoundingBox":
        return cls(min(box.x0 for box in boxes), min(box.y0 for box in boxes), max(box.x1 for box in boxes), max(box.y1 for box in boxes))


@dataclass(frozen=True)
class Token:
    extraction_ordinal: int
    text: str
    bbox: BoundingBox


@dataclass(frozen=True)
class Line:
    ordinal: int
    token_ordinals: tuple[int, ...]
    bbox: BoundingBox


@dataclass(frozen=True)
class Page:
    ordinal: int
    width: Decimal
    height: Decimal
    tokens: tuple[Token, ...]
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class TdcPdfGir:
    gir_version: str
    profile_version: str
    pages: tuple[Page, ...]


def nfc_source_text(value: str) -> str:
    """Apply only the frozen source-text normalization."""
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    return unicodedata.normalize("NFC", value)


def recognition_key(value: str) -> str:
    """Normalize structural labels without mutating retained source text."""
    value = unicodedata.normalize("NFKC", nfc_source_text(value)).casefold()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", value).strip()


def extract_tdc_pdf(source: str | Path | bytes | BinaryIO) -> TdcPdfGir:
    """Extract a readable, native-text, US-Letter PDF into canonical GIR."""
    data = _read_source(source)
    # The marker is part of the PDF trailer/object vocabulary and lets us
    # classify password-protected input before a reader emits implementation-
    # specific password exceptions. It is not source content inspection.
    if b"/Encrypt" in data:
        raise ExtractionError(ConformanceCode.ENCRYPTED_PDF)
    try:
        with pdfplumber.open(__import__("io").BytesIO(data), laparams=None) as pdf:
            if getattr(pdf, "stream", None) is not None and getattr(pdf.stream, "isEncrypted", False):
                raise ExtractionError(ConformanceCode.ENCRYPTED_PDF)
            pages: list[Page] = []
            for ordinal, page in enumerate(pdf.pages, 1):
                pages.append(_extract_page(page, ordinal))
    except ExtractionError:
        raise
    except Exception as exc:
        name = type(exc).__name__.lower()
        code = ConformanceCode.ENCRYPTED_PDF if "password" in name or "encrypt" in name else ConformanceCode.INVALID_PDF
        raise ExtractionError(code) from None
    if not pages or not any(page.tokens for page in pages):
        raise ExtractionError(ConformanceCode.NATIVE_TEXT_UNAVAILABLE)
    return TdcPdfGir(GIR_VERSION, PROFILE_VERSION, tuple(pages))


def _read_source(source: str | Path | bytes | BinaryIO) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if isinstance(source, bytes):
        return source
    data = source.read()
    if not isinstance(data, bytes):
        raise TypeError("source must provide bytes")
    return data


def _extract_page(page, ordinal: int) -> Page:
    width = Decimal(str(page.width)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    height = Decimal(str(page.height)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    if (width, height) != _LETTER:
        raise ExtractionError(ConformanceCode.UNSUPPORTED_PAGE_GEOMETRY)
    try:
        words = page.extract_words(
            x_tolerance=3, y_tolerance=3, line_dir="ttb", char_dir="ltr",
            keep_blank_chars=False, use_text_flow=False, return_chars=True,
        )
    except Exception:
        raise ExtractionError(ConformanceCode.PAGE_ACCESS_FAILED) from None
    tokens = tuple(
        Token(index, nfc_source_text(word.get("text", "")), BoundingBox.from_pdf_word(word, width, height))
        for index, word in enumerate(words, 1) if nfc_source_text(word.get("text", ""))
    )
    tokens = tuple(sorted(tokens, key=lambda token: (token.bbox.y0, token.bbox.x0, token.bbox.x1, token.extraction_ordinal)))
    return Page(ordinal, width, height, tokens, _group_lines(tokens))


def _group_lines(tokens: tuple[Token, ...]) -> tuple[Line, ...]:
    groups: list[list[Token]] = []
    centers: list[Decimal] = []
    for token in tokens:
        center = (token.bbox.y0 + token.bbox.y1) / 2
        compatible = [(abs(center - line_center), index) for index, line_center in enumerate(centers) if abs(center - line_center) <= Decimal("2.00")]
        if compatible:
            _, index = min(compatible, key=lambda item: (item[0], item[1]))
            groups[index].append(token)
            centers[index] = sum(((item.bbox.y0 + item.bbox.y1) / 2 for item in groups[index]), Decimal("0")) / len(groups[index])
        else:
            groups.append([token])
            centers.append(center)
    groups.sort(key=lambda group: (min(item.bbox.y0 for item in group), min(item.bbox.x0 for item in group), min(item.extraction_ordinal for item in group)))
    return tuple(Line(index, tuple(item.extraction_ordinal for item in sorted(group, key=lambda item: (item.bbox.x0, item.bbox.x1, item.extraction_ordinal))), BoundingBox.union(tuple(item.bbox for item in group))) for index, group in enumerate(groups, 1))


def _canonical(gir: TdcPdfGir) -> dict:
    return {"gir_version": gir.gir_version, "profile_version": gir.profile_version, "pages": [
        {"ordinal": page.ordinal, "width": str(page.width), "height": str(page.height),
         "tokens": [{"ordinal": token.extraction_ordinal, "text": token.text, "bbox": token.bbox.as_list()} for token in page.tokens],
         "lines": [{"ordinal": line.ordinal, "token_ordinals": list(line.token_ordinals), "bbox": line.bbox.as_list()} for line in page.lines]}
        for page in gir.pages
    ]}


def canonical_hash(gir: TdcPdfGir) -> str:
    payload = json.dumps(_canonical(gir), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()
