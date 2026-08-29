"""Deterministic native-text extraction for the BCI Historical PDF GIR."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import unicodedata
from typing import BinaryIO

import pdfplumber


GIR_VERSION = "BCI-HIST-PDF-GIR-v1"
EXTRACTION_PROFILE_VERSION = "bci-historical-pdf-profile-v1"
_QUANTUM = Decimal("0.01")
_LETTER = (Decimal("612.00"), Decimal("792.00"))


class BciHistoricalExtractionError(Exception):
    """Safe extraction failure; no source text is included."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


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
        return [format(value, "f") for value in (self.x0, self.y0, self.x1, self.y1)]

    @classmethod
    def from_word(cls, word: dict, width: Decimal, height: Decimal) -> "BoundingBox":
        values = [Decimal(str(word[key])) for key in ("x0", "top", "x1", "bottom")]
        values = [max(Decimal("0"), min(value, limit)) for value, limit in zip(values, (width, height, width, height))]
        return cls(*values)

    @classmethod
    def union(cls, boxes: tuple["BoundingBox", ...]) -> "BoundingBox":
        return cls(
            min(box.x0 for box in boxes),
            min(box.y0 for box in boxes),
            max(box.x1 for box in boxes),
            max(box.y1 for box in boxes),
        )


@dataclass(frozen=True, repr=False)
class Token:
    extraction_ordinal: int
    text: str
    bbox: BoundingBox

    def __repr__(self) -> str:
        return f"Token(extraction_ordinal={self.extraction_ordinal}, text=<redacted>)"


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


@dataclass(frozen=True, repr=False)
class BciHistoricalPdfGir:
    gir_version: str
    extraction_profile_version: str
    pages: tuple[Page, ...]

    @property
    def profile_version(self) -> str:
        return self.extraction_profile_version

    def __repr__(self) -> str:
        return f"BciHistoricalPdfGir(pages={len(self.pages)}, gir_version={self.gir_version!r})"


def nfc_source_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    return unicodedata.normalize("NFC", value)


def recognition_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", nfc_source_text(value)).casefold()
    value = "".join(char for char in unicodedata.normalize("NFD", value) if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip()


def extract_bci_historical_pdf(source: bytes | BinaryIO | str | Path) -> BciHistoricalPdfGir:
    data = _read_source(source)
    if not data.startswith(b"%PDF-"):
        raise BciHistoricalExtractionError("pdf_invalid")
    if b"/Encrypt" in data:
        raise BciHistoricalExtractionError("pdf_encrypted_unsupported")
    try:
        with pdfplumber.open(io.BytesIO(data), laparams=None) as pdf:
            if getattr(pdf, "stream", None) is not None and getattr(pdf.stream, "isEncrypted", False):
                raise BciHistoricalExtractionError("pdf_encrypted_unsupported")
            pages = tuple(_extract_page(page, ordinal) for ordinal, page in enumerate(pdf.pages, 1))
    except BciHistoricalExtractionError:
        raise
    except Exception:
        raise BciHistoricalExtractionError("pdf_invalid") from None
    if not pages or not any(page.tokens for page in pages):
        raise BciHistoricalExtractionError("native_text_required")
    return BciHistoricalPdfGir(GIR_VERSION, EXTRACTION_PROFILE_VERSION, pages)


def _read_source(source: bytes | BinaryIO | str | Path) -> bytes:
    if isinstance(source, (str, Path)):
        try:
            return Path(source).read_bytes()
        except Exception:
            raise BciHistoricalExtractionError("pdf_invalid") from None
    if type(source) is bytes:
        return source
    try:
        data = source.read()
    except Exception:
        raise BciHistoricalExtractionError("pdf_invalid") from None
    if type(data) is not bytes:
        raise BciHistoricalExtractionError("pdf_invalid")
    return data


def _extract_page(page, ordinal: int) -> Page:
    width = Decimal(str(page.width)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    height = Decimal(str(page.height)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    if (width, height) != _LETTER:
        raise BciHistoricalExtractionError("source_variant_unsupported")
    try:
        words = page.extract_words(
            x_tolerance=3,
            y_tolerance=3,
            line_dir="ttb",
            char_dir="ltr",
            keep_blank_chars=False,
            use_text_flow=False,
            return_chars=True,
        )
    except Exception:
        raise BciHistoricalExtractionError("page_access_failed") from None
    tokens = tuple(
        Token(index, nfc_source_text(word.get("text", "")), BoundingBox.from_word(word, width, height))
        for index, word in enumerate(words, 1)
        if nfc_source_text(word.get("text", ""))
    )
    ordered = tuple(sorted(tokens, key=lambda token: (token.bbox.y0, token.bbox.x0, token.bbox.x1, token.extraction_ordinal)))
    return Page(ordinal, width, height, ordered, _group_lines(ordered))


def _group_lines(tokens: tuple[Token, ...]) -> tuple[Line, ...]:
    groups: list[list[Token]] = []
    centers: list[Decimal] = []
    for token in tokens:
        center = (token.bbox.y0 + token.bbox.y1) / 2
        compatible = [(abs(center - value), index) for index, value in enumerate(centers) if abs(center - value) <= Decimal("2.00")]
        if compatible:
            _, index = min(compatible, key=lambda item: (item[0], item[1]))
            groups[index].append(token)
            centers[index] = sum(((item.bbox.y0 + item.bbox.y1) / 2 for item in groups[index]), Decimal("0")) / len(groups[index])
        else:
            groups.append([token])
            centers.append(center)
    groups.sort(key=lambda group: (min(item.bbox.y0 for item in group), min(item.bbox.x0 for item in group), min(item.extraction_ordinal for item in group)))
    return tuple(
        Line(index, tuple(item.extraction_ordinal for item in sorted(group, key=lambda item: (item.bbox.x0, item.bbox.x1, item.extraction_ordinal))), BoundingBox.union(tuple(item.bbox for item in group)))
        for index, group in enumerate(groups, 1)
    )


def canonical_hash(gir: BciHistoricalPdfGir) -> str:
    payload = {
        "gir_version": gir.gir_version,
        "extraction_profile_version": gir.extraction_profile_version,
        "pages": [
            {
                "ordinal": page.ordinal,
                "width": format(page.width, "f"),
                "height": format(page.height, "f"),
                "tokens": [{"ordinal": token.extraction_ordinal, "text": token.text, "bbox": token.bbox.as_list()} for token in page.tokens],
                "lines": [{"ordinal": line.ordinal, "token_ordinals": list(line.token_ordinals), "bbox": line.bbox.as_list()} for line in page.lines],
            }
            for page in gir.pages
        ],
    }
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
