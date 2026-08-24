"""Source-specific Santander credit-card PDF extraction and parser."""

from .extraction import (
    GIR_VERSION,
    PROFILE_VERSION,
    BoundingBox,
    ConformanceCode,
    ExtractionError,
    Line,
    Page,
    TdcPdfGir,
    Token,
    canonical_hash,
    extract_tdc_pdf,
    nfc_source_text,
    recognition_key,
)
from .parser import (
    PARSER_VERSION, SOURCE_VARIANT, ContradictoryTdcPdfError,
    TdcPdfParserError, UnsupportedTdcPdfError, parse_tdc_pdf, parse_tdc_pdf_gir,
)
from .types import (
    AdditionalPageSpan, FieldProvenance, FinancialCategory, ParserStatus, ReconciliationEvidence,
    ReconciliationStatus, RowOutcome, SectionState, SourceRecord,
    StatementMetadata, TdcPdfParserResult,
)

__all__ = [
    "BoundingBox", "ConformanceCode", "ExtractionError", "GIR_VERSION",
    "Line", "PROFILE_VERSION", "Page", "TdcPdfGir", "Token",
    "canonical_hash", "extract_tdc_pdf", "nfc_source_text", "recognition_key",
    "PARSER_VERSION", "SOURCE_VARIANT", "parse_tdc_pdf", "parse_tdc_pdf_gir",
    "TdcPdfParserError", "UnsupportedTdcPdfError", "ContradictoryTdcPdfError",
    "AdditionalPageSpan", "FieldProvenance", "FinancialCategory", "ParserStatus", "ReconciliationEvidence",
    "ReconciliationStatus", "RowOutcome", "SectionState", "SourceRecord",
    "StatementMetadata", "TdcPdfParserResult",
]
