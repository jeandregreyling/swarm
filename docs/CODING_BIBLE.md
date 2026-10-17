# Coding Bible — Swarm Engineering Rules

Version: 1.0.0

This document is the local fallback for the Coding Bible. Studio/Knowledge
Center is the primary editable copy; prompt generation uses this file when the
Studio copy is unavailable.

## Engineering principles

- Make the smallest correct change that fully solves the problem.
- Fix root causes; do not mask failures with broad catches, silent defaults, or
  weakened assertions.
- Preserve existing behavior and follow nearby patterns. Keep changes focused.
- Never push or commit changes without explicit authorization.
- Do not expose credentials, tokens, or private user data in logs or responses.

## Repository and runtime

- Resolve database connections through `utils.db._connection`; honor
  `SWARM_DB_PATH` instead of hard-coding a database path.
- Load local environment configuration through the shared environment loader.
  Existing process environment variables take precedence over local files.
- Keep route handlers in the existing Flask blueprint structure and cover
  endpoint changes with focused tests.
- Use the repository's configured service ports and process manager; do not
  assume a developer-specific path, host, or service name.

## Frontend

- Follow existing template, JavaScript, and CSS conventions.
- When changing a versioned frontend asset, update its cache-busting version
  where the asset is included.
- Use accessible controls and the existing design system; use SVG icons rather
  than emoji in shipped UI.

## Testing and maintenance

- Run the narrowest relevant tests first, then expand validation as needed.
- Tests should assert observable behavior rather than incidental source layout.
- Keep test databases isolated and patch the module object actually used by the
  application.
- Update related documentation when behavior or operational guidance changes.

## Agent Role Matrix

- **Gemma** — General-purpose assistant and decision maker.
- **LLaMA** — Research and fast first-pass analysis.
- **Mistral** — Focused, small coding changes.
- **Twenty** — Multi-file coding and deeper refactoring.
- **Eight** — SAP HCM, Payroll, and ABAP specialist.
- **Eleven** — Concise independent second opinion.
- **Librarian** — Indexes and tags knowledge; does not answer users directly.
- **Duck** — Coordinates handoffs when an answer needs additional review.
- **Vortex** — Preserves workflow and decision traceability.

Treat the role matrix as routing guidance, not as a reason to bypass agent
availability, safety, or user authorization.

## 10. Coder Persona Quick Card

```text
CODING BIBLE — quick rules:
- Smallest correct change; fix root causes, don't hide failures.
- Use utils.db._connection for swarm_memory.db and honor SWARM_DB_PATH.
- Preserve behavior and follow local project conventions.
- Test the behavior changed, starting with focused tests.
- Do not expose secrets or commit/push without explicit authorization.
- Keep frontend changes accessible and update asset cache versions as needed.
```
