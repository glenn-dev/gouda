"""BCI Current Cartola legacy-XLS v0.1 source parser."""

from .parser import (
    CONTRACT_VERSION,
    PARSER_VERSION,
    SOURCE_VARIANT,
    AmbiguousWorksheetError,
    BciCurrentCartolaParserError,
    MalformedWorkbookError,
    UnsupportedWorkbookError,
    parse_bci_current_cartola_xls,
)
from .types import ParseResult, ParserStatus, RowOutcome, SourceCell, SourceRecord

__all__ = [
    "CONTRACT_VERSION",
    "PARSER_VERSION",
    "SOURCE_VARIANT",
    "AmbiguousWorksheetError",
    "BciCurrentCartolaParserError",
    "MalformedWorkbookError",
    "ParseResult",
    "ParserStatus",
    "RowOutcome",
    "SourceCell",
    "SourceRecord",
    "UnsupportedWorkbookError",
    "parse_bci_current_cartola_xls",
]
