# BERA handoff: where the work stands

Branch `claude/modest-faraday-z032dy`, last commit `3914f6a`. Everything below is committed and pushed
except this file. Last full runs: server 5516 passed, web 923 passed, secret scan and ruff clean.
Working standards are in `CLAUDE.md` (read it first: tests with every change, shared `AppError`, no
hard-coded platform values, no helper text on pages, popups with `Dialog`, tokens only, `/design`
shows every building block, README section per ticket, run `python scripts/scan_secrets.py` and the
tests before every push, no PR unless asked).

## 1. Tickets, one by one

Done, pushed, with tests and a README section each (older ones first):

| Ticket | What |
| --- | --- |
| 089 to 104 | Security suite, team invites and management, admin login (two-step), admin roles, audit log, security event alerts, company activity log, plans, regional pricing, subscription states, usage counting, limit enforcement, usage and plan display, admin limit and subscription controls, block a team member |
| 105 to 110 | Create, list, edit, archive and delete projects; requirement extraction from the job description; requirement editor; project scoring settings |
| 111 to 120 | Bulk CV upload, file checks, private file storage, duplicate detection, text reading, background processing, AI reading, fairness guard, candidate record, candidate data protection |
| 121 to 131 | Model settings, prompt versions, requirement evaluation, score calculation (124, plus a later fix so a scored CV counts against the monthly limit), ATS score, extra scoring factors, recommendation and insights, AI usage tracking, cost estimate before processing, re-scoring, AI outage handling and kill switch |
| 132 to 135 | Ranked candidate list, filters, candidate detail, stages and notes |
| 136 | Comparison view (side by side and matrix) |
| 137 | Top-N list with ties |
| 139 | Share report (read-only link, expiry, revoke, views) |
| 140 | Live updates (calm polling, offline notice) |
| 141 | Dashboard charts (funnel, distribution, ranking, coverage, trend) |

**Not in my records: BERA-138.** The ticket batch jumped from 137 to 139. If 138 exists it was never
sent to me, so it is not built. Tickets before 089 are the foundation (see `git log`). No ticket after
141 has been received; 142 to 145 below are my own labels for the extra work.

## 2. Extra work done beyond the tickets (labels 142 to 145)

All of it came from the owner's requests after BERA-141 (reference images, "make it real, clickable,
with hover details", "use tabs"). Nothing here was a numbered ticket, so review it as such.

**BERA-142 Company dashboard** (`server/cvs/dashboard.py`, `web/src/components/company/dashboard/`)
- Cards with change against the previous period (CVs uploaded, scored, shortlisted, average score),
  three insight cards, two donuts, a gauge, top candidates (with compare), quick actions, pending
  actions, live activity. Period buttons (today, week, month), export as CSV or a printable page.
- Every card and chart mark has a hover tooltip; most open a popup listing what was counted, each
  name a link. Endpoints: `GET /api/company/dashboard/`, `.../detail/`, `.../report/` (`&as=csv`).
- Chart colours as tokens (green, blue, violet, amber, coral, teal, grey, plus soft tints and text
  colours) in `tokens.css`, pairs checked in `design-rules.test.ts`. Dark mode keeps the original cards.
- New UI pieces: `SegmentedControl`, `Tooltip` takes any node, `ChartMark`/`TipLines` (hover/focus
  details), `DetailDialog`, `Sparkline`, `Donut`, `Gauge`, `KpiCard`, `InsightCard`, `timeAgo`.
- The existing project charts (funnel, grades, ranking, coverage, trend) were redrawn with the new
  colours, hover details and click popups; the trend got gridlines and a dot and tooltip per day.
- 7 platform settings: `dashboard.*`.

**BERA-143 Candidate comparison, part two** (`server/cvs/comparison.py`, `frontier.py`,
`web/src/components/company/comparison/`)
- Candidate cards, sentence insights (lead, tie, missing must-have, clearly best), requirement bars
  per candidate, evidence popup (requirement, verdict, confidence, quote), Pareto frontier chart
  (AI against ATS, or must-have against nice-to-have) with linked dots and "Compare the frontier".
- Definitions of terms appear on hover or focus only (`terms.tsx`), to respect "no helper text".
- `GET /api/company/projects/<id>/frontier/?axes=`; side-by-side answer gained scores per group,
  counts, `insights`, `points`, `confidence`. Setting `comparison.frontier_max_points`.

**BERA-144 Tabs** (`web/src/lib/useTabParam.ts`)
- Company dashboard (Overview, Projects, Candidates, Usage, Activity) and the comparison (Overview,
  Requirements, Frontier, Evidence; Matrix and Frontier on the matrix page) are split into tabs, kept
  in the address. Company "Usage" tab shows plan limits (owner only) and the trend.

**BERA-145 Admin overview** (`server/adminusers/overview.py`, `web/src/components/admin/dashboard/`)
- Tabs Overview, Revenue, Usage, AI, Attention; platform card, estimated monthly revenue and margin,
  plan mix, subscription states, scoring pace, busiest companies, AI calls by purpose and model,
  token budget, pending actions, newest companies; popups link to `/admin/companies/<id>`; CSV and
  printable report. Support admins get counts and usage only (server leaves money and AI out).
- `GET /api/admin/dashboard/`, `.../detail/`, `.../report/`. 5 settings `admin_dashboard.*`.

**Small refactors made along the way:** `scoring._points` became `verdict_points`; `charts._per_day`
and `_change` became public `per_day` and `percent_change`; `cvs/dashboard` helpers `windows`,
`in_days`, `card` are public; `TrendCard` takes any metrics and an optional period; `Gauge`, `KpiCard`
and `ExportDialog` take labels, formats and an area.

**Images only (not in the repo):** screenshots of the product pages, colour palette, chart colour
options and the dashboard mock-ups were made as PNGs for the owner to choose from. Nothing in the repo
depends on them.

## 3. Decisions and assumptions to keep

- Candidate names are shown as initials (`mask_name`) everywhere, also on the dashboards.
- Exports hold projects and counts, never candidate names; CSV cells that look like formulas are
  quoted.
- "Revenue" is an estimate: the prices of paying plans (active, past due within grace, cancelled until
  the period ends). There are no payment records, so no history and no "money received".
- Time to shortlist is measured from the candidate being added to the first move to Shortlisted.
- The funnel steps after "scored" count candidates that ever reached the stage, so it never grows.
- Live endpoints use their own rate limit (`rate_limits.live_updates_per_minute`).
- Earlier owner decisions still apply: no two-step reset for companies, a reason is required for admin
  actions, security events only in the audit log, the activity list is owner only, no PDF/DOCX job
  description file in 105, no hand-made PDF checks.
- One known flaky test: `signin/tests/test_login.py::TestTheAddressLimit::test_the_eleventh_attempt...`
  depends on the wall-clock minute; it passes alone.

## 4. Still to do

Needs a new table or model:
- **Payments table** (Stripe events, amounts, dates). Without it there is no revenue history, no
  month-by-month revenue against AI cost, and `/admin/operations/payments` stays empty.
- **A "shortlisted at" record** (or reading the stage history more cheaply) if the time-to-shortlist
  figure must be exact at scale.
- **Data requests and jobs on the admin Attention tab** (their models exist as separate tickets;
  the overview does not read them yet).
- A rule and, if needed, a table change for removing a team member who wrote notes or moved stages
  (those links are PROTECT).

Pages or features still open:
- Company dashboard is done; the project Overview page still shows five charts above the upload area
  (could be tabs like the rest).
- The Candidates tab's "Upload CVs" and "Download all" buttons are placeholders.
- Matrix cells have hover only (the matrix answer carries no evidence); side-by-side has the popup.
- The admin panel still uses a placeholder session (`placeholder-session.ts`, role fixed to super);
  the overview works from the server's answer, but the sidebar does not yet read the real role.
- The cost estimate popup has no Upgrade or Renewal buttons.
- `plans.subscriptions.expire_lapsed_subscriptions` and `activity.service.purge_expired_entries` are
  not scheduled.
- CI has never run on GitHub (workflow exists in spirit, never executed).
- The optional theme-switch question was never answered; do not act without a reply.
- Pareto chart and the detail popups are not on `/design` (they need server data).

## 5. How to continue

```bash
cd /home/user/BERA/server && pg_isready || pg_ctlcluster 16 main start
.venv/bin/ruff format . -q && .venv/bin/ruff check . --fix
.venv/bin/python -m pytest -q -m "not network"          # about 5 minutes
cd ../web && npx prettier --write src && npx tsc --noEmit && npx vitest run
cd .. && git add -A && python scripts/scan_secrets.py
```

Add new settings to `server/platform_settings/definitions.py` and to
`platform_settings/tests/test_definitions.py::EXPECTED_DEFAULTS`; add new colour pairs to
`web/src/styles/design-rules.test.ts`; add a README section per ticket; commit with the two
trailers (`Co-Authored-By`, `Claude-Session`) on the branch above; push; no pull request unless asked.
