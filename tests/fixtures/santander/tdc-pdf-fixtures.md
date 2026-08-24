# Synthetic Santander TDC PDF fixtures

The extraction tests generate PDFs in memory with ReportLab. They contain only
synthetic labels, dates, descriptions, references, and amounts. No private PDF
is copied, sanitized, or used as a fixture source.

The cases cover three- and four-page Letter documents, repeated structural
headers, multiline row-shaped text, page boundaries, unsupported geometry,
image-only/native-text absence, malformed bytes, and deterministic repeated
extraction. Financial row parsing is intentionally not part of this fixture
set.
