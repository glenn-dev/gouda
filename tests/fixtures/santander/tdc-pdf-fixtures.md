# Synthetic Santander TDC PDF fixtures

The extraction tests generate PDFs in memory with ReportLab. They contain only
synthetic labels, dates, descriptions, references, and amounts. No private PDF
is copied, sanitized, or used as a fixture source.

The cases cover three- and four-page Letter documents, repeated structural
headers, multiline row-shaped text, page boundaries, unsupported geometry,
image-only/native-text absence, malformed bytes, and deterministic repeated
extraction. Parser tests build additional all-synthetic PDFs in memory for
billed domestic/international/installment, payment, credit, financial-charge,
and unbilled/future rows; exact Decimal amounts; immutable result graphs;
section-local ordinals; complete field provenance; explicit statement/row
currency; multi-line and repeated multi-line headers; authorized and rejected
page-boundary continuations; summary-only reconciliation; contradictory state
transitions; unknown headings; conflicting monetary columns; and malformed
financial candidates. No private PDF is used as a template or persisted as a
fixture. The parser fixtures also cover the observed national-currency dual-
amount layout: original USD operation evidence remains separate from the CLP
`Cargo del mes`, which alone drives `debt_effect`. Synthetic masked-card
identity contexts exercise leading-zero preservation, repeated agreement,
sanitized conflicts, and movement-heading ignore behavior.
