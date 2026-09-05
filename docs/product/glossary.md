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

**Classification** — An explicit, revisable category assignment to an accepted
Movement, separate from financial facts, economic-event meaning, and provider
metadata. MVP persistence is frozen but not implemented; see
[Movement classification](../architecture/movement-classification.md).

**Category** — A local dataset topic grouping with a stable UUID and display
name. A Movement has zero or one current category; a category has no inherent
income/expense type or sign.

**Unclassified / uncategorized** — No current category is assigned. An absent
assignment row means never assigned; a retained null-category row means
cleared. Both are unclassified, not a category or a completed-review state.

**Economic meaning** — What an event represents, such as income, spending,
refund, adjustment, or transfer. It cannot be inferred from signed amount
alone and has no persisted type in the first classification slice.

**Transfer** — A shared event between own accounts represented by account
Movements. A future verified relationship establishes the relevant own-account
scope and excludes transfer effects from consolidated income/spending. Gouda
has no ownership or transfer persistence yet; a category cannot establish
either relationship.

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
