from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

from gouda.santander_tdc_pdf import (
    BoundingBox,
    ConformanceCode,
    ExtractionError,
    GIR_VERSION,
    PROFILE_VERSION,
    Token,
    canonical_hash,
    extract_tdc_pdf,
    nfc_source_text,
    recognition_key,
)
from gouda.santander_tdc_pdf.extraction import _group_lines


def synthetic_pdf(page_count: int, *, image_only: bool = False, repeated_header: bool = False) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=LETTER)
    for page_number in range(1, page_count + 1):
        if image_only:
            image = Image.new("RGB", (80, 40), "white")
            image_buffer = BytesIO()
            image.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            from reportlab.lib.utils import ImageReader
            document.drawImage(ImageReader(image_buffer), 48, 700, width=80, height=40)
        else:
            document.setFont("Helvetica", 10)
            document.drawString(48, 750, "Santander Tarjeta Crédito - Estado de cuenta")
            document.drawString(48, 732, "Periodo: Enero 2026   Fecha corte: 31/01/2026")
            document.drawString(48, 714, "Fecha   Detalle / referencia                         CLP       Monto")
            if repeated_header:
                document.drawString(48, 696, "Fecha   Detalle / referencia                         CLP       Monto")
            document.drawString(48, 678, f"0{page_number}/01   COMPRA SINTETICA {page_number}              CLP       1234,56")
            document.drawString(48, 660, "continuación de descripción multilinea")
            document.drawString(48, 642, "Pago vence: 15/02/2026")
        document.showPage()
    document.save()
    return output.getvalue()


class SantanderTdcPdfExtractionTests(unittest.TestCase):
    def test_profile_and_gir_identity(self):
        gir = extract_tdc_pdf(synthetic_pdf(3))
        self.assertEqual(gir.gir_version, GIR_VERSION)
        self.assertEqual(gir.profile_version, PROFILE_VERSION)
        self.assertEqual([page.ordinal for page in gir.pages], [1, 2, 3])

    def test_three_and_four_page_letter_documents(self):
        for page_count in (3, 4):
            gir = extract_tdc_pdf(synthetic_pdf(page_count))
            self.assertEqual(len(gir.pages), page_count)
            self.assertTrue(all((page.width, page.height) == (612, 792) for page in gir.pages))

    def test_normalization_preserves_source_and_separates_recognition_key(self):
        source = "Café\r\n12\u00a0345,67"
        self.assertEqual(nfc_source_text(source), "Café\n12 345,67")
        self.assertEqual(recognition_key("  CAFE\u0301   12 345,67 "), "cafe 12 345,67")

    def test_tokens_lines_and_geometry_are_deterministic(self):
        first = extract_tdc_pdf(synthetic_pdf(3))
        second = extract_tdc_pdf(synthetic_pdf(3))
        self.assertEqual(canonical_hash(first), canonical_hash(second))
        page = first.pages[0]
        self.assertTrue(all(value == value.quantize(__import__("decimal").Decimal("0.01")) for token in page.tokens for value in (token.bbox.x0, token.bbox.y0, token.bbox.x1, token.bbox.y1)))
        self.assertLess(page.lines[0].bbox.y0, page.lines[-1].bbox.y0)
        for line in page.lines:
            self.assertEqual(line.bbox, BoundingBox.union(tuple(page.tokens[ordinal - 1].bbox for ordinal in line.token_ordinals)))
            self.assertEqual(list(line.token_ordinals), sorted(line.token_ordinals, key=lambda ordinal: page.tokens[ordinal - 1].bbox.x0))

    def test_exact_tie_uses_earlier_line_and_words_sort_left_to_right(self):
        tokens = (
            Token(1, "right", BoundingBox(20, 10, 30, 12)),
            Token(2, "lower", BoundingBox(5, 14, 15, 16)),
            Token(3, "tie", BoundingBox(40, 12, 50, 14)),
        )
        lines = _group_lines(tokens)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].token_ordinals, (1, 3))

    def test_repeated_header_multiline_and_page_boundary_are_structural_only(self):
        gir = extract_tdc_pdf(synthetic_pdf(4, repeated_header=True))
        self.assertEqual(len(gir.pages), 4)
        self.assertTrue(all(len(page.lines) >= 4 for page in gir.pages))
        self.assertFalse(any(hasattr(page, "row_groups") for page in gir.pages))

    def test_unsupported_geometry(self):
        output = BytesIO()
        document = canvas.Canvas(output, pagesize=landscape(LETTER))
        document.drawString(20, 20, "synthetic")
        document.save()
        with self.assertRaises(ExtractionError) as context:
            extract_tdc_pdf(output.getvalue())
        self.assertEqual(context.exception.code, ConformanceCode.UNSUPPORTED_PAGE_GEOMETRY)
        self.assertNotIn("synthetic", str(context.exception))

    def test_no_native_text_and_invalid_pdf(self):
        with self.assertRaises(ExtractionError) as image_error:
            extract_tdc_pdf(synthetic_pdf(1, image_only=True))
        self.assertEqual(image_error.exception.code, ConformanceCode.NATIVE_TEXT_UNAVAILABLE)
        with self.assertRaises(ExtractionError) as invalid_error:
            extract_tdc_pdf(b"not a pdf")
        self.assertEqual(invalid_error.exception.code, ConformanceCode.INVALID_PDF)
        self.assertNotIn("not a pdf", str(invalid_error.exception))

    def test_encrypted_pdf_fails_at_conformance_boundary(self):
        writer = PdfWriter()
        for page in PdfReader(BytesIO(synthetic_pdf(1))).pages:
            writer.add_page(page)
        writer.encrypt("synthetic-password")
        encrypted = BytesIO()
        writer.write(encrypted)
        with self.assertRaises(ExtractionError) as context:
            extract_tdc_pdf(encrypted.getvalue())
        self.assertEqual(context.exception.code, ConformanceCode.ENCRYPTED_PDF)

    def test_fixture_generation_is_not_a_private_source_dependency(self):
        self.assertFalse(any(Path("tests/fixtures").rglob("*.pdf")))


if __name__ == "__main__":
    unittest.main()
