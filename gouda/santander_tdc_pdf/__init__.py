"""Source-specific Santander credit-card PDF extraction."""

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

__all__ = [
    "BoundingBox", "ConformanceCode", "ExtractionError", "GIR_VERSION",
    "Line", "PROFILE_VERSION", "Page", "TdcPdfGir", "Token",
    "canonical_hash", "extract_tdc_pdf", "nfc_source_text", "recognition_key",
]
