"""Bounded, non-semantic admission for private browser-uploaded XLSX bytes."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
import re
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException


MAX_ARCHIVE_ENTRIES = 128
MAX_TOTAL_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_ENTRY_EXPANDED_BYTES = 10 * 1024 * 1024
MAX_WORKSHEETS = 4
MAX_WORKSHEET_ROWS = 10_000
MAX_WORKSHEET_COLUMNS = 64
MAX_RECTANGULAR_CELLS = 100_000
MAX_XML_DEPTH = 64
MAX_XML_ELEMENTS = 500_000

_CELL_REFERENCE = re.compile(r"^\$?([A-Z]{1,3})\$?([1-9][0-9]*)$")
_RANGE_REFERENCE = re.compile(
    r"^\$?([A-Z]{1,3})\$?([1-9][0-9]*)(?::\$?([A-Z]{1,3})\$?([1-9][0-9]*))?$"
)


class XlsxAdmissionError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass
class _SheetExtent:
    max_row: int = 0
    max_column: int = 0
    inferred_row: int = 0
    inferred_column: int = 0

    def include(self, row: int, column: int) -> None:
        if row > MAX_WORKSHEET_ROWS or column > MAX_WORKSHEET_COLUMNS:
            raise XlsxAdmissionError("statement_resource_limit")
        self.max_row = max(self.max_row, row)
        self.max_column = max(self.max_column, column)


class _BoundedEntryReader:
    """Count actual decompression while exposing only the file interface used by XML."""

    def __init__(self, source, *, total_counter: list[int]):
        self._source = source
        self._entry_count = 0
        self._total_counter = total_counter

    def read(self, size=-1):
        chunk = self._source.read(size)
        self._entry_count += len(chunk)
        self._total_counter[0] += len(chunk)
        if (
            self._entry_count > MAX_ENTRY_EXPANDED_BYTES
            or self._total_counter[0] > MAX_TOTAL_EXPANDED_BYTES
        ):
            raise XlsxAdmissionError("statement_resource_limit")
        return chunk

    def close(self):
        self._source.close()


def admit_xlsx_package(content: bytes) -> None:
    """Reject malformed or allocation-hostile OOXML before openpyxl sees it.

    This validates packaging and resource bounds only. Santander recognition
    remains inside the existing importer and parser contract.
    """

    try:
        with ZipFile(BytesIO(content), "r") as archive:
            infos = archive.infolist()
            if not infos:
                raise XlsxAdmissionError("xlsx_invalid")
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise XlsxAdmissionError("statement_resource_limit")

            seen: set[str] = set()
            for info in infos:
                name = _validate_member_name(info.filename)
                if name in seen:
                    raise XlsxAdmissionError("xlsx_invalid")
                seen.add(name)
                if info.flag_bits & 0x1:
                    raise XlsxAdmissionError("xlsx_invalid")
                if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                    raise XlsxAdmissionError("xlsx_invalid")
                if info.file_size > MAX_ENTRY_EXPANDED_BYTES:
                    raise XlsxAdmissionError("statement_resource_limit")
                if _is_macro_member(name):
                    raise XlsxAdmissionError("xlsx_invalid")

            if sum(info.file_size for info in infos) > MAX_TOTAL_EXPANDED_BYTES:
                raise XlsxAdmissionError("statement_resource_limit")
            # First pass reaches EOF for every entry, validating actual expanded
            # size and CRC without retaining extracted package data.
            total_counter = [0]
            for info in infos:
                with archive.open(info, "r") as source:
                    reader = _BoundedEntryReader(source, total_counter=total_counter)
                    while reader.read(64 * 1024):
                        pass

            if "[Content_Types].xml" not in seen:
                raise XlsxAdmissionError("xlsx_invalid")
            element_counter = [0]
            declared_worksheets = _declared_worksheet_names(archive, element_counter)
            if not declared_worksheets or any(name not in seen for name in declared_worksheets):
                raise XlsxAdmissionError("xlsx_invalid")
            if len(declared_worksheets) > MAX_WORKSHEETS:
                raise XlsxAdmissionError("statement_resource_limit")

            total_rectangular_cells = 0
            actual_worksheets = set()
            for info in infos:
                name = info.filename
                if not (name.endswith(".xml") or name.endswith(".rels")):
                    continue
                if name == "[Content_Types].xml":
                    continue
                # Inspect every XML part as a possible worksheet so a hostile
                # relationship cannot route openpyxl around path/content-type
                # based limits.
                extent = _SheetExtent()
                with archive.open(info, "r") as source:
                    is_worksheet = _inspect_xml(
                        source,
                        extent=extent,
                        element_counter=element_counter,
                    )
                if is_worksheet:
                    actual_worksheets.add(name)
                    total_rectangular_cells += extent.max_row * extent.max_column
                    if total_rectangular_cells > MAX_RECTANGULAR_CELLS:
                        raise XlsxAdmissionError("statement_resource_limit")

            if len(actual_worksheets) > MAX_WORKSHEETS:
                raise XlsxAdmissionError("statement_resource_limit")
            if "xl/workbook.xml" not in seen or not declared_worksheets.issubset(actual_worksheets):
                raise XlsxAdmissionError("xlsx_invalid")
    except XlsxAdmissionError:
        raise
    except (BadZipFile, DefusedXmlException, OSError, RuntimeError, ValueError, EOFError):
        raise XlsxAdmissionError("xlsx_invalid") from None
    except Exception:
        raise XlsxAdmissionError("xlsx_invalid") from None


def _validate_member_name(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise XlsxAdmissionError("xlsx_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise XlsxAdmissionError("xlsx_invalid")
    normalized = path.as_posix()
    if normalized != value.rstrip("/") and not value.endswith("/"):
        raise XlsxAdmissionError("xlsx_invalid")
    return normalized


def _is_macro_member(name: str) -> bool:
    lower = name.lower()
    return (
        lower.endswith(".bin")
        or "vbaproject" in lower
        or lower.startswith("xl/embeddings/")
        or lower.startswith("xl/activeX/".lower())
    )


def _declared_worksheet_names(archive: ZipFile, element_counter: list[int]) -> set[str]:
    result = set()
    depth = 0
    root_name = None
    with archive.open("[Content_Types].xml", "r") as source:
        parser = SafeElementTree.iterparse(
            source,
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        for event, element in parser:
            local = element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""
            if event == "end":
                depth -= 1
                element.clear()
                continue
            depth += 1
            if depth == 1:
                root_name = local
            element_counter[0] += 1
            if depth > MAX_XML_DEPTH or element_counter[0] > MAX_XML_ELEMENTS:
                raise XlsxAdmissionError("statement_resource_limit")
            if local == "Relationship" and element.attrib.get("TargetMode", "").lower() == "external":
                raise XlsxAdmissionError("xlsx_invalid")
            if local in {"Default", "Override"}:
                content_type = element.attrib.get("ContentType", "").lower()
                if "macroenabled" in content_type or "vba" in content_type:
                    raise XlsxAdmissionError("xlsx_invalid")
            if local != "Override":
                continue
            if content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml":
                part_name = element.attrib.get("PartName", "")
                if not part_name.startswith("/"):
                    raise XlsxAdmissionError("xlsx_invalid")
                result.add(_validate_member_name(part_name[1:]))
    if depth != 0 or root_name != "Types":
        raise XlsxAdmissionError("xlsx_invalid")
    return result


def _inspect_xml(source, *, extent, element_counter) -> bool:
    depth = 0
    current_row = 0
    current_column = 0
    root_name = None
    parser = SafeElementTree.iterparse(
        source,
        events=("start", "end"),
        forbid_dtd=True,
        forbid_entities=True,
        forbid_external=True,
    )
    for event, element in parser:
        local = element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""
        if event == "start":
            depth += 1
            if depth == 1:
                root_name = local
            element_counter[0] += 1
            if depth > MAX_XML_DEPTH or element_counter[0] > MAX_XML_ELEMENTS:
                raise XlsxAdmissionError("statement_resource_limit")
            if local == "Relationship" and element.attrib.get("TargetMode", "").lower() == "external":
                raise XlsxAdmissionError("xlsx_invalid")
            if extent is not None and root_name == "worksheet":
                if local == "row":
                    supplied = element.attrib.get("r")
                    current_row = _positive_index(supplied) if supplied is not None else current_row + 1
                    current_column = 0
                    extent.include(current_row, max(current_column, 1))
                elif local == "c":
                    reference = element.attrib.get("r")
                    if reference is None:
                        current_column += 1
                        extent.include(max(current_row, 1), current_column)
                    else:
                        row, column = _cell_extent(reference)
                        current_row = max(current_row, row)
                        current_column = column
                        extent.include(row, column)
                elif local in {"dimension", "mergeCell"}:
                    reference = element.attrib.get("ref")
                    if not reference:
                        raise XlsxAdmissionError("xlsx_invalid")
                    row, column = _range_extent(reference)
                    extent.include(row, column)
        else:
            depth -= 1
            element.clear()
    if depth != 0:
        raise XlsxAdmissionError("xlsx_invalid")
    return root_name == "worksheet"


def _positive_index(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or value.startswith("0"):
        raise XlsxAdmissionError("xlsx_invalid")
    return int(value)


def _column_number(value: str) -> int:
    result = 0
    for character in value:
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def _cell_extent(value: str) -> tuple[int, int]:
    match = _CELL_REFERENCE.fullmatch(value)
    if match is None:
        raise XlsxAdmissionError("xlsx_invalid")
    return int(match.group(2)), _column_number(match.group(1))


def _range_extent(value: str) -> tuple[int, int]:
    match = _RANGE_REFERENCE.fullmatch(value)
    if match is None:
        raise XlsxAdmissionError("xlsx_invalid")
    row = max(int(match.group(2)), int(match.group(4) or match.group(2)))
    column = max(_column_number(match.group(1)), _column_number(match.group(3) or match.group(1)))
    return row, column
