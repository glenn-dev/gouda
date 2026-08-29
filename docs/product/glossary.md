# Glossary

**Account** — A financial container, such as a checking account or credit card.

**Artifact** — Exact source content received by Gouda, preserved independently
from whether it can be identified, interpreted, or accepted.

**Evidence** — Source material and provenance that may support, contradict, or
remain unrelated to an interpreted or canonical financial fact.

**Financial observation** — An interpreted financial claim derived from one
source record before or alongside canonical acceptance. Its claim fields are
immutable through supported application-service and ordinary model-save
writes. It may remain unresolved, be rejected, conflict with a known canonical
movement, support a movement, or be superseded by a corrected interpretation.

**Movement** — A canonical financial change accepted by Gouda for an account.
Its signed amount is positive when the account's contribution to household net
worth increases and negative when it decreases. A movement is not provisional.

**Signed amount** — The normalized numeric value that captures direction as well as magnitude.

**Transfer** — A movement between two accounts owned by the same user; it should not be counted as income or spending in consolidated totals.

**Provisional view** — An explicitly labeled view that may combine canonical
movements with unresolved recent evidence. It is not an authoritative or
reconciled ledger total.

**Resolution** — An append-only auditable decision that rejects an observation,
confirms a new movement, links support to an existing movement, records a
conflict with a known canonical movement, reopens review, or supersedes an
interpretation. Generic ambiguity remains unresolved. Canonical movement
correction is a separate deferred lifecycle.

**Source authority** — The contextual strength of evidence for a particular
field or use. It is not one universal numeric score.

**Source record** — An immutable record-oriented interpretation retained for
traceability. A parsed source record is not universally equivalent to a
canonical movement.

**Provenance** — Metadata describing where a normalized value came from and how it was derived.

**Abstention** — An explicit decision not to interpret or resolve evidence when
the available facts are insufficient or materially ambiguous.

**Reconciliation** — Comparing imported movements and derived balances with an external account statement or known balance.
