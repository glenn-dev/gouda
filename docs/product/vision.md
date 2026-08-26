# Product vision

Gouda makes personal financial movement understandable without requiring users to reconcile multiple account views manually.

The product centers on a trustworthy movement ledger and an evidence-first
ingestion experience. It preserves source facts even when they cannot yet be
interpreted confidently, keeps interpreted evidence separate from accepted
financial truth, and expresses each canonical movement with an explicit sign.

Gouda gives users a consistent way to answer:

- Where did money come from and where did it go?
- How did balances and spending change over time?
- Which movements are transfers, income, expenses, or adjustments?
- Can every derived insight be traced back to source data?

Recent or incomplete evidence may support an explicitly provisional view, but
must not silently alter authoritative totals. Several pieces of evidence may
support one canonical fact.

Trust is a product feature: imports and interpretations are explainable,
uncertainty is visible, corrections are auditable, unsupported inputs can be
preserved without being guessed into the ledger, and sensitive data is handled
conservatively. AI may reduce ingestion friction, while deterministic rules
remain responsible for accounting correctness.

The stable principles are defined in
[Ingestion and evidence principles](ingestion-evidence-principles.md).
