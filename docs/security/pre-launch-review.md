# Pre-launch security review (BERA-181)

Date: 2026-11-25. Every item is **passing** or **accepted**. Nothing is accepted now.
Run it again before any later launch step with the commands in the last column.

| # | Item | Result | How to run it again |
|---|------|--------|---------------------|
| 1 | Known weaknesses in production libraries (server: pip-audit; web: `npm audit --omit=dev`) | Passing: 0 findings | `python scripts/check_vulnerabilities.py` |
| 2 | Accepted development-tool findings (the vitest chain: vitest, vite, vite-node, @vitest/mocker, tinypool, esbuild) | Passing: upgraded to vitest 5.1.2 and vite 8, which cleared all six. The acceptances were removed, so none is left to re-date | same command; `security/accepted-vulnerabilities.toml` is empty |
| 3 | Secrets in the project | Passing: no secret in any tracked file. Four lines in two early commits are fake test values (`test_required_secrets.py`, two sign-in tests), since marked as fake; no real value was ever committed | `python scripts/scan_secrets.py` |
| 4 | Company isolation: a company can never reach another company's data | Passing: 108 tests | `python -m pytest -m isolation` |
| 5 | Security suite: every server route attacked (no sign-in, forged, expired, wrong kind of token, ended session, blocked person, suspended company), role matrix, rate limits, hostile input | Passing: 5344 tests | `python -m pytest -m security` |
| 6 | Permission on every page: who may open each `/company` and `/admin` page | Passing: `web/src/app/page-permissions.test.ts` lists every page with its roles and fails when a page has no decision. The server enforces the same roles on every route (item 5), so hiding a page is never the only protection | `npx vitest run src/app/page-permissions.test.ts` |
| 7 | Whole suites | Passing: server 8607 tests, web 1431 tests, plus typecheck, formatting and the secret scan | `python -m pytest` and `npx vitest run` |

## What changed for item 2

The risks were: a test UI or dev server that can read files, and a worker pool that could run
code. They only ever ran on a developer's computer and in the automatic tests. The upgrade removes
the question. `@vitejs/plugin-react` moved to 6.3.0 and `vitest.config.ts` became
`vitest.config.mts` (vite 8 prefers a module config file).

## Not checked here

This review covers the code and its libraries. The things only the real server can show are
listed in the README under each earlier ticket (server security, backups, monitoring). Run
`python scripts/scan_public_address.py https://your-address --origin-ip SERVER_IP` once the
site is live and add its result here.
