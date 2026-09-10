from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from django.test import SimpleTestCase

from gouda.ledger.xlsx_admission import XlsxAdmissionError, admit_xlsx_package


FIXTURE = Path(__file__).parents[1] / "fixtures" / "santander" / "synthetic-current-account.xlsx"


def rewrite_entry(content, name, replacement):
    target = BytesIO()
    with ZipFile(BytesIO(content), "r") as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
        for info in source.infolist():
            output.writestr(info.filename, replacement if info.filename == name else source.read(info))
    return target.getvalue()


class XlsxAdmissionTests(SimpleTestCase):
    def setUp(self):
        self.content = FIXTURE.read_bytes()

    def assert_code(self, content, code):
        with self.assertRaises(XlsxAdmissionError) as caught:
            admit_xlsx_package(content)
        self.assertEqual(caught.exception.code, code)

    def test_known_synthetic_workbook_is_admitted(self):
        admit_xlsx_package(self.content)

    def test_malformed_encrypted_like_and_macro_packages_are_rejected(self):
        self.assert_code(b"not a zip", "xlsx_invalid")
        self.assert_code(b"\xd0\xcf\x11\xe0" + b"encrypted" * 10, "xlsx_invalid")
        target = BytesIO()
        with ZipFile(BytesIO(self.content), "r") as source, ZipFile(target, "w") as output:
            for info in source.infolist():
                output.writestr(info.filename, source.read(info))
            output.writestr("xl/vbaProject.bin", b"synthetic")
        self.assert_code(target.getvalue(), "xlsx_invalid")

    def test_sparse_dimension_merge_and_row_claims_are_resource_bounded(self):
        worksheet = "xl/worksheets/sheet1.xml"
        for marker in (
            b'<dimension ref="A1:XFD1048576"/>',
            b'<mergeCells count="1"><mergeCell ref="A1:B10001"/></mergeCells>',
            b'<sheetData><row r="10001"><c r="A10001"/></row></sheetData>',
        ):
            xml = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + marker + b"</worksheet>"
            self.assert_code(rewrite_entry(self.content, worksheet, xml), "statement_resource_limit")

        target = BytesIO()
        disguised = (
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<dimension ref="A1:XFD1048576"/></worksheet>'
        )
        with ZipFile(BytesIO(self.content), "r") as source, ZipFile(target, "w") as output:
            for info in source.infolist():
                output.writestr(info.filename, source.read(info))
            output.writestr("xl/disguised.xml", disguised)
        self.assert_code(target.getvalue(), "statement_resource_limit")

    def test_dtd_and_entity_are_rejected_by_safe_xml_reader(self):
        xml = b'<!DOCTYPE worksheet [<!ENTITY x "synthetic">]><worksheet>&x;</worksheet>'
        self.assert_code(
            rewrite_entry(self.content, "xl/worksheets/sheet1.xml", xml),
            "xlsx_invalid",
        )

    def test_content_types_is_inside_xml_depth_and_element_bounds(self):
        content_types = (
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + b"<Default Extension=\"xml\" ContentType=\"application/xml\"/>" * 8
            + b"</Types>"
        )
        with patch("gouda.ledger.xlsx_admission.MAX_XML_ELEMENTS", 5):
            self.assert_code(
                rewrite_entry(self.content, "[Content_Types].xml", content_types),
                "statement_resource_limit",
            )

    def test_entry_count_and_expanded_size_are_bounded(self):
        target = BytesIO()
        with ZipFile(BytesIO(self.content), "r") as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(info.filename, source.read(info))
            for index in range(129):
                output.writestr(f"synthetic/{index}.txt", b"x")
        self.assert_code(target.getvalue(), "statement_resource_limit")

        target = BytesIO()
        with ZipFile(BytesIO(self.content), "r") as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
            for info in source.infolist():
                output.writestr(info.filename, source.read(info))
            output.writestr("synthetic/large.txt", b"x" * (10 * 1024 * 1024 + 1))
        self.assert_code(target.getvalue(), "statement_resource_limit")

    def test_duplicate_and_unsafe_member_names_are_rejected(self):
        for name in ("../synthetic.xml", "xl\\synthetic.xml"):
            target = BytesIO()
            with ZipFile(BytesIO(self.content), "r") as source, ZipFile(target, "w") as output:
                for info in source.infolist():
                    output.writestr(info.filename, source.read(info))
                output.writestr(name, b"<x/>")
            self.assert_code(target.getvalue(), "xlsx_invalid")
