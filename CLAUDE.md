# BERA — Working Standards

These rules apply to every ticket and every work session. They are not optional.
If a ticket cannot be done within these rules, stop, explain which rule conflicts
and why, and ask before proceeding. Never bend a rule silently.

## Workflow
- Work on one ticket at a time. Briefly describe the approach before building.
- Keep each change small and focused on the ticket. No unrelated refactors or
  drive-by changes; raise them as separate suggestions instead.
- Ask instead of guessing when requirements are unclear or ambiguous.

## Code quality
- Write clean, readable code. Prefer simple and explicit over clever.
- Use meaningful, descriptive names for files, functions, variables, and types.
  Avoid abbreviations and generic names (`data`, `tmp`, `handle`, `util`).
- Do not duplicate logic. Before writing something new, search for an existing
  implementation and reuse or extend it.
- Keep functions and modules small, each with a single responsibility.
- Comment *why*, not *what*. Remove dead and commented-out code.

## Testing
- Every feature ships with automated tests in the same change.
- Tests must cover the happy path **and every edge case listed in the ticket**.
- Bug fixes include a test that fails before the fix and passes after it.
- All tests must pass before committing. Never skip, disable, or delete a test
  to make the suite pass.

## Error reporting
- Use one consistent error-reporting mechanism across the whole project: a
  single shared error type/helper, defined once and reused everywhere.
- Every error carries a stable machine-readable `code`, a human-readable
  `message`, and optional non-sensitive `details`.
- Never swallow errors silently. Either handle them meaningfully or propagate
  them through the shared mechanism.
- Error messages shown to users must not leak internals (stack traces, queries,
  file paths, secrets).

## Secrets and personal data
- Never put secrets (API keys, passwords, tokens, private keys, connection
  strings) in code, tests, fixtures, docs, or commit history. Load them from
  environment variables or a secret manager; `.env` files are never committed.
- Never log secrets or personal data (names, emails, phone numbers, addresses,
  IDs, payment details). Mask or omit them in logs and error details.
- Test data must be obviously fake (e.g. `user@example.com`).

## Definition of done
A ticket is done only when:
1. The change is limited to the ticket's scope.
2. Tests for the feature and all listed edge cases exist and pass.
3. Errors go through the shared error mechanism.
4. No secrets or personal data appear in code or logs.
5. The change is committed with a clear, descriptive message.

## Technology decisions (apply to all tickets)
- Server: Python, Django + Django REST Framework. PostgreSQL database.
  Background jobs: Django-Q2 using PostgreSQL as the queue (no Redis for now).
- UI: Next.js + TypeScript, one app with three areas: public website (`/`),
  company panel (`/company`), admin panel (`/admin`).
- Sign-in: JWT with short-lived access tokens and refresh tokens (see the
  Security foundation tickets).
- AI: OpenAI API. Models and prices are configured from the admin panel,
  never hard-coded.
- File storage: S3-compatible (Cloudflare R2) in production; a local private
  folder in development.
- Payments: Stripe, test mode first.
- Local development: Windows, local PostgreSQL, one command (`python scripts/dev.py`).
- Hosting later: one Linux server holding staging and production side by side.
- Tooling: pytest + pytest-django and ruff (Python); Vitest + Testing Library
  and Prettier (web). For unlisted tooling choose the standard, popular option,
  keep it simple, and mention the choice briefly instead of asking.
