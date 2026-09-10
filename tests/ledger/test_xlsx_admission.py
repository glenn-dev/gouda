from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree

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

    def test_workbook_sheet_aliases_cannot_multiply_allocations(self):
        with ZipFile(BytesIO(self.content)) as archive:
            root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = root.find("{*}sheets")
        original = dict(sheets[0].attrib)
        for index in range(2, 7):
            ElementTree.SubElement(sheets, sheets[0].tag, {
                **original, "name": f"Synthetic{index}", "sheetId": str(index), "state": "hidden",
            })
        self.assert_code(rewrite_entry(self.content, "xl/workbook.xml", ElementTree.tostring(root)),
                         "statement_resource_limit")

    def test_hyperlink_ranges_participate_in_allocation_bounds(self):
        with ZipFile(BytesIO(self.content)) as archive:
            xml = archive.read("xl/worksheets/sheet1.xml")
        for reference in (b"A1:A10001", b"A1:BM2", b"A1:AX3000"):
            modified = xml.replace(b"</worksheet>", b'<hyperlinks><hyperlink ref="' + reference
                                   + b'" location="A1"/></hyperlinks></worksheet>')
            self.assert_code(rewrite_entry(self.content, "xl/worksheets/sheet1.xml", modified),
                             "statement_resource_limit")

    def test_relationship_targets_cannot_hide_xml_from_inspection(self):
        target = BytesIO()
        with ZipFile(BytesIO(self.content)) as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
            for info in source.infolist():
                data = source.read(info)
                if info.filename == "xl/_rels/workbook.xml.rels":
                    data = data.replace(b"worksheets/sheet1.xml", b"worksheets/hidden.data")
                output.writestr(info.filename, data)
            output.writestr("xl/worksheets/hidden.data", b'<worksheet><dimension ref="A1:XFD1048576"/></worksheet>')
        self.assert_code(target.getvalue(), "xlsx_invalid")

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

    def test_namespace_name_expansion_is_rejected_before_tree_allocation(self):
        xml = b'<worksheet xmlns:p="urn:' + b"x" * 2048 + b'">'
        xml += b"".join(f"<p:item{index}/>".encode() for index in range(1000))
        xml += b"</worksheet>"
        self.assert_code(rewrite_entry(self.content, "xl/worksheets/sheet1.xml", xml),
                         "statement_resource_limit")

    def test_shared_string_references_cannot_amplify_parser_text(self):
        target = BytesIO()
        sheet = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        sheet += b"".join(f'<row r="{i}"><c r="C{i}" t="s"><v>0</v></c></row>'.encode() for i in range(1, 4001))
        sheet += b'</sheetData></worksheet>'
        with ZipFile(BytesIO(self.content)) as source, ZipFile(target, "w", ZIP_DEFLATED) as output:
            for info in source.infolist():
                if info.filename == "xl/sharedStrings.xml":
                    continue
                output.writestr(info.filename, sheet if info.filename == "xl/worksheets/sheet1.xml" else source.read(info))
            output.writestr("xl/sharedStrings.xml", b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>'
                            + b" " + b"x" * 6000 + b" </t></si></sst>")
        self.assert_code(target.getvalue(), "statement_resource_limit")

    def test_style_text_references_cannot_amplify_row_evidence(self):
        from openpyxl import Workbook
        workbook = Workbook()
        number_format = '"' + "x" * (2 * 1024 * 1024) + '"'
        for index in range(1, 4):
            cell = workbook.active.cell(index, 1, 1)
            cell.number_format = number_format
        target = BytesIO()
        workbook.save(target)
        workbook.close()
        self.assert_code(target.getvalue(), "statement_resource_limit")

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
