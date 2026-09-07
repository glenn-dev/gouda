# Current task

## Objective

Independently review the committed local HTTP classification write boundary.
The decision remains frozen in
[ADR-0012](../../docs/decisions/ADR-0012-local-classification-write-boundary.md);
the backend/runtime/delivery-edge slice is implemented and reviewed. The review
found and corrected an Accept-negotiation mismatch plus stale implementation
status documentation. Amend the authorized single signed commit
`feat: implement local classification write boundary`; do not push.

## Baseline

After `git fetch origin`, clean `main`, HEAD, and `origin/main` all matched
`bb09f7c0d281f68010baed9ed56055b45a02b88e`
(`docs: define local classification write boundary`), with a good local ED25519
Git signature.

The independent review fetched and verified clean `main` at
`e7223f47040312785bda9d4e1416da98bb0e5421`, exactly one commit ahead of that
unchanged origin baseline, with the expected title and a valid SSH signature.

## Current state

- The backend now implements the separate write runtime/grant, bootstrap,
  authorized orchestration, and strict PATCH. React remains read-only. No model,
  migration, domain transition command, or Compose topology changed.
- ADR-0012 records independent default-off write activation, a separate opaque
  runtime/grant, process-lifetime capability, explicit bootstrap, exact
  Origin/Host checks, and one Account-scoped classification PATCH contract.
- Principal identity remains server-issued and orthogonal to write authority.
  Read access or UUID possession alone cannot authorize mutation. Arbitrary
  local processes/users remain trusted under ADR-0010; the new token is not
  protection against a hostile local host.
- The implementation preserves all domain revision/no-op/locking semantics,
  exact errors, and a transaction-consistent classification-only response.
  HTTP never silently retries. Full bigint revisions remain lossless.
- First write topology is the existing IPv4 Vite edge at port 5173 for host
  development or Compose. IPv6 backend reads remain supported; no IPv6 write
  topology is implicitly added. ADR-0010 and ADR-0011 text is unchanged.

## Validation state

Focused/security/HTTP/PostgreSQL concurrency tests, complete Django regression,
frontend tests/typecheck/build/dependencies, live host/Compose/browser/restart
checks, and documentation/privacy/diff checks are recorded in `.ai/handoff.md`.
Validation uses only isolated synthetic databases; no private evidence is read.
The corrected backend passes 173 affected tests and the complete 523-test suite.
The frontend's 38 tests, typecheck, and build pass. Live host, Compose, direct
Django, real browser, and process-restart checks verify the transport boundary.

## Next bounded scope

The backend slice is complete. Follow with a separate React editor task covering
explicit manual choices, memory-only capability handling, safe
integer submissions, and 409/ambiguous-outcome reconciliation.
Recommended reasoning level: High.

## Non-goals

No React editor, migrations, or pushes in this checkpoint. Filtering, Category management,
default taxonomy, demo assignments, automatic/rule/AI assignments, bulk edits,
history, ownership, transfer or income/expense semantics remain deferred.
