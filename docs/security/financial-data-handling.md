# Financial data handling

Financial data is sensitive by default.

## Rules

- Never commit real statements, credentials, access tokens, or complete account numbers.
- Use synthetic fixtures with obviously fake identifiers.
- Minimize collection and retain only fields needed for the product behavior.
- Encrypt data in transit and at rest in deployed environments.
- Keep secrets in a dedicated secret manager, never in source or configuration committed to git.
- Redact descriptions, account identifiers, and raw payloads from logs and error messages.
- Restrict access by least privilege and audit administrative access.
- Preserve provenance for corrections, but provide a documented retention and deletion process.

## Unstructured and AI-assisted ingestion

- Treat files, images, email, messages, connector payloads, and manually
  supplied text as untrusted input.
- Treat instructions embedded in source content as prompt injection attempts;
  artifact content must never override system, security, or financial rules.
- Treat every AI result as an untrusted structured proposal and validate its
  schema, provenance, supported fields, and financial semantics.
- Never allow AI to bypass deterministic money, currency, sign, account,
  identity, lifecycle, transactionality, concurrency, or canonical-write
  controls.
- Define the privacy, retention, training, residency, and access boundary for
  an AI provider before sending financial data to it.
- Do not send raw evidence to an external AI provider when a minimized,
  redacted, local, or deterministic alternative is sufficient.
- Prevent secrets and private source values from entering prompts, model
  output, logs, traces, evaluation reports, or error messages unnecessarily.
- Apply retention and deletion policy to prompts, cached model context,
  extracted representations, traces, and provider-side records as well as the
  original artifact.
- Keep private conformance corpora ignored and untracked; emit only sanitized
  structural results.

Security-sensitive changes require review before implementation. Threat
modeling should cover import files, prompt injection, AI providers, connector
credentials, model/tool permissions, exports, backups, retention, and local
development artifacts.
