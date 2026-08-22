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

Security-sensitive changes require review before implementation. Threat modeling should cover import files, connector credentials, exports, backups, and local development artifacts.
