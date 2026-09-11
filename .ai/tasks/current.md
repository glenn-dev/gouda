# Current task

## Completed acceptance task

On 2026-09-10, the first controlled private real-data acceptance of the
Santander Current Account XLSX local import flow passed. The sanitized evidence,
demonstrated behavior, and explicit unvalidated scope are recorded in
`docs/development/local-import-adversarial-review.md`.

## Next bounded objective

Implement the manual Movement classification editor within the already accepted
ADR-0012 write boundary. Start from the frozen classification architecture and
current read-only React projection; do not fold filtering, economic types,
transfer semantics, another import source, or broader authentication into this
checkpoint.
