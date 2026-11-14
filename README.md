# BERA

One repository, two sides:

- `server/` — API and background jobs (Python, Django REST Framework, Django-Q2 on PostgreSQL)
- `web/` — one Next.js app with three separate areas: website (`/`), company panel (`/company`), admin panel (`/admin`)

The engineering rules and technology decisions are in [CLAUDE.md](CLAUDE.md).

## Run it locally (Windows, PowerShell)

### One-time installs (all free)

1. [Python 3.11+](https://www.python.org/downloads/) — tick "Add python.exe to PATH"
2. [Node.js LTS](https://nodejs.org/)
3. A database, either:
   - **Docker Desktop** (preferred; nothing else to configure), or
   - **PostgreSQL 16** from <https://www.postgresql.org/download/windows/>:
     keep port 5432, remember the `postgres` password, add its `bin` folder to `PATH`,
     and keep it listening on this computer only (the installer default).

### Start everything

```powershell
python scripts/dev.py
```

The first run does the setup by itself: creates `.env` (fake local values) from `.env.example`,
installs Python and web packages, starts the database (Docker if available, otherwise your
native PostgreSQL), applies database changes, and creates a fake admin and fake company.
Running it again is safe and keeps your data.

With native PostgreSQL, the first run stops once and asks you to put the `postgres` password
into `POSTGRES_ADMIN_PASSWORD` in `.env`; run the command again afterwards.

When ready it prints:

| Area          | Address                             |
| ------------- | ----------------------------------- |
| Website       | http://localhost:3000/              |
| Company panel | http://localhost:3000/company       |
| Admin panel   | http://localhost:3000/admin         |
| API health    | http://localhost:8000/api/health/   |

Press `Ctrl+C` to stop everything.

Fake accounts (development only): admin `admin@example.test` / `FAKE-admin-password-dev-only`
and company owner `owner@example.test` / `FAKE-company-password-dev-only`. There are three
separate kinds of account: companies, company users and admin users (see
`server/companies` and `server/adminusers`); they share no table. Passwords are stored only as
Argon2 hashes. A local database from before this change needs `python scripts/dev.py reset-db`.

### Other commands

```powershell
python scripts/dev.py reset-db   # empties the local database (asks first), then re-creates it
python scripts/dev.py test       # runs all tests (server, scripts and web)
```

If a port (3000, 8000, 5432) is busy or a tool is missing, the command says what to do.

## Settings and secrets

Settings come only from environment variables. `APP_ENV` must be `development`, `staging`
or `production`. Locally they are read from `.env`, which is git-ignored; `.env.example`
lists every setting with fake values.

The central list of required settings is `RequiredSetting` entries in `server/config/secrets.py`.
In staging and production the app refuses to start if any entry is missing or a secret is still
a placeholder (such as the fake values in `.env.example`); it names the settings, never their
values. Development only needs `DJANGO_SECRET_KEY`, `DATABASE_URL`, `MIGRATION_DATABASE_URL`,
`JWT_COMPANY_SECRET`, `JWT_ADMIN_SECRET`, `FIELD_ENCRYPTION_KEY` and `FIELD_HASH_KEY` (the token
secrets, and the two field keys, must each be at least 32 characters and different from each
other). The app never holds `MIGRATION_DATABASE_URL` and the migration step never holds
`DATABASE_URL`. Staging and production also need `TRUSTED_PROXY_COUNT`, `ALLOWED_HOSTS` and
`ALLOWED_ORIGINS` (the https addresses of the website, the only sites allowed to use the API from
a browser), and every database address must end with `?sslmode=verify-full` (or `verify-ca`,
`require`) so the connection is encrypted. Staging and production must use different values for every secret.

A ticket that adds a feature with its own key (AI, payments, email, storage) adds the key to
that list, to `.env.example` (fake value) and to this section, in the same change.

Every change is scanned for secrets by `python scripts/scan_secrets.py` (also part of the test
command and of the automatic checks in `.github/workflows/checks.yml`). A fake value on purpose
needs "fake", "example" or "test-only" in its line, or a `nosecret` comment. If a key leaks,
follow [docs/security/if-a-key-leaks.md](docs/security/if-a-key-leaks.md).

`seed_dev_data` and `reset_dev_db` refuse to run outside development.

### Sign up

`POST /api/auth/company/signup/` (the page is `/signup`) creates a company and its owner and
sends the verification email. It is limited to 5 per hour per address, needs a password of at
least 12 characters that is not commonly used, and the Terms ticked. It answers "If this email
can be used, we have sent instructions." whether or not the email already has an account; an
existing account is sent a notice instead (at most 3 per hour per inbox). The owner stays
unverified until the verification ticket's link is used, and login (its own ticket) must refuse
unverified owners.

The form suggests the visitor's country from Cloudflare's `CF-IPCountry` header, believed only
for requests that came through our own proxies (`TRUSTED_PROXY_COUNT`); anything unknown
becomes Other (`ZZ`). Locally set `DEVELOPMENT_PRETEND_COUNTRY=PK` in `.env` to pretend a
country; staging and production ignore it.

### Login

`POST /api/auth/company/login/` (the page is `/login`, with `?next=` for the page originally
wanted, only ever a `/company` page) checks the email and password and starts a new session
with protected cookies; every device has its own session. Wrong email, wrong password, a
blocked or removed person and a person without a password all get "Email or password is
incorrect.", take the same time (a password is always hashed and compared) and count the same
toward the pause: `signin.max_failed_attempts` (5) within `signin.attempt_window_minutes` (15)
pause the account for `signin.lockout_minutes` (15), even for the right password. Only with the
right password does a person learn "Your company account is suspended. Please contact
support." or "Please verify your email" (with a resend button). The existing login limit of
10 per minute per address applies as well. Passwords are only in the request body, never in
addresses or logs.

### Password rules and changing a password

The rules live once, in `core/passwords.py`: at least `passwords.min_length` (12) and at most
`passwords.max_length` (128) characters, and not one of the 20,000 most used passwords
(`passwords.block_common_passwords`). Sign up, reset and the Profile page all refuse a weak
password with every reason at once, and the team-invite acceptance will use the same
`PasswordField`. `POST /api/auth/password-check/` reports which rules a typed text meets; the
sign up, reset, invite and Profile pages show that as live hints and, where there is a confirm
field, say live whether the two entries match.

Profile → Change password (`POST /api/auth/company/change-password/`, signed in) takes the
current password, the new one and its confirmation. The current password is checked first; a
wrong one gets one plain message and no hints, and counts toward the same pause as wrong
guesses at the login page (5 in 15 minutes pause the account for 15 minutes). A change ends
every session of the person, starts a fresh one for this device, and sends the "password
changed" email.

### Forgot and reset password

`/forgot-password` (`POST /api/auth/company/forgot-password/`) always answers "If an account
exists, we sent a reset link", is limited to 5 per hour per email (any spelling, known or not)
and sends the link only to active accounts. The link (`/reset-password?token=…`) is a
`LinkToken` for resetting a password: random, stored only as a hash, valid for one hour
(`tokens.password_reset_hours`), usable once, and a newer link cancels older ones.
`POST …/reset-password/` takes the token and the new password twice. The shared password rules
apply, and the new password may not be the old one; a refused password does not use up the
link. A successful reset ends every session of the person, sends the "password changed"
email, and signs nobody in. An expired or used link shows its message with a "Request a new
link" button.

### Logging out and ending sessions

`POST /api/auth/company/logout/` (and `/admin/`) ends the session named by the refresh cookie and
clears the cookies. It works after the short-lived token has ended and is safe to repeat.
`POST …/logout-all/` ends every session of the signed-in person. A session also ends, at once
and for good (being active again later does not bring it back), when its person is blocked or
removed, or changes their password: the change-password and reset flows then start a fresh
session for the device in use. A session ends by itself when its refresh token expires, and a
revoked session's tokens are refused on the very next request.

In the web app, a request refused with "not signed in" first tries to renew the session once;
if that fails the person goes to the login page and comes back to the same page afterwards.
Upload screens call `startUpload()` from `lib/session.ts` and the returned function when the
file is done; while one runs, an ended session shows a warning instead of leaving the page.
"Log out" is in the user menu and "Sign out of all devices" on the Profile page.

### Email verification

The link in the sign-up email opens `/verify-email?token=…`. Opening it changes nothing; the
"Verify email" button sends `POST /api/auth/company/verify-email/`, so mail programs that open
links to check them cannot use it up. A link works once, for 24 hours
(`tokens.email_verification_hours`), and only for verifying: the secret is random and stored
only as a hash in the shared `LinkToken` table, which the reset and invite tickets reuse through
`consume_link_token`. An expired, used or unknown link shows its own message and a resend form.
Whoever is signed in is left alone; the link alone decides which email is verified.

"Resend verification email" (`/verify-email` without a token, linked from the login page) asks
for the email address and always answers the same way. It sends a new link only to an active,
unverified account, cancels the older links, and is limited to 3 per hour per email
(`rate_limits.verification_resend_per_hour`).

### System emails

All system emails go through `send_email(template, address, **values)` in `server/emailing`.
The eight templates (verify email, reset password, team invite, password changed, email
changed, new sign-in, usage notice, payment problem) share one layout with the Bera name, one
main button and a plain-text version; the words are in `emailing/catalog.py`. Links must point
to `WEB_BASE_URL` and can never carry a password (`emailing/links.py`). A provider failure is
retried after 1, 5 and 30 minutes (`email.retry_waits_seconds`), then logged; it never breaks
the user's action. Addresses the provider rejects are recorded and skipped from then on.

In development nothing is sent: messages are saved as `.eml` files in `.dev-inbox/` (open them
with any mail program or text editor). `python manage.py send_test_emails` (in `server/`) puts
one of each template there. Staging and production send through SMTP and need `EMAIL_HOST`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_FROM_ADDRESS` (the one sender) and
`WEB_BASE_URL` (https). Webhooks that report bounces depend on the provider chosen and are not
built yet; `record_bounce` is what they will call.

### Sign-in safety notices and two-step verification

**Notices.** The person whose account it is gets an email when a sign-in comes from a device
or country not seen before (`signin/new_sign_in.py`), when the password changes, and when the
email address changes. The first sign-in is the baseline and sends nothing. A device is the
browser and system (for example "Firefox on Windows"), a place is the country from the
Cloudflare header (see Sign up); where the country is unknown it is Other and never counts as
a new place. Only the device text and the country are kept, never an address. The "email
changed" email goes to the address the person had before; the future email-change flow
**must** call `send_email_changed_notice(person, previous_address)` in
`companies/account_notices.py` once the new address is saved.

**Two-step verification** (authenticator app, `twostep/`). The owner switches it on under
Advanced → Security: scan the QR code (or type the key), give a code from the app, and get
`two_step.recovery_code_count` (10) one-time recovery codes, shown once and stored only as
keyed hashes. The secret is stored encrypted (`FIELD_ENCRYPTION_KEY`). Login with it takes two
steps: the right password returns `two_step_required` and a signed challenge (valid
`two_step.challenge_minutes`, 10), and only a right code (or an unused recovery code) at
`/api/auth/company/login/two-step/` starts the session. A code can be used only once; codes
from `two_step.code_drift_steps` (1) steps either side of now are accepted. Wrong codes pause
the account like wrong passwords, with a count of their own so logging in again does not reset
it. Turning it off needs the password and a code.

**Company-wide requirement.** An owner can require it for all members
(`PUT /api/auth/company/two-step/company-requirement/`). A member without it gets
`two_step_setup_required` at their next login and no session until they have set it up. While
it is required, members cannot turn it off. Owners are not forced.

**Lost device.** A recovery code replaces the app code once. A person with neither device nor
codes sees "Lost your device and your recovery codes? Contact support." Recovery by support
(after identity checks, audited) is not built: it needs the audit log (BERA-094) and the admin
panel's login and roles (BERA-092, BERA-093), and comes with the admin controls ticket.

### Route protection and roles

Every company request is checked on the server. The one check reads the session, the person
and the company in a single lookup: the session must be live, the person must be active and
belong to the session's company, and the company must be active. Suspending a company or
blocking or removing a person stops their tokens at once, and ends their sessions so lifting
the block later does not bring them back. The **role is read from the stored account on every
request**, never from the token, so a role change applies immediately (a renewed token also
carries the current role).

What each role may do is written once, in `companies/role_matrix.py`: the owner can do
everything; a member can create, edit and archive projects, upload and download CVs, view
candidates, change stages, write notes, delete individual candidates, and download and share
reports, but cannot invite or remove people, see Usage and Billing, change company settings,
open Advanced, delete projects or delete the company. A view names its action
(`required_action = "team.invite"` on a `CompanyObjectView`, or `require_action(user, action)`
in a function view) and never lists roles. `companies/tests/test_role_matrix.py` repeats the
rules from the ticket and tests every action for both roles; a change to a rule must change
that list too.

The web menu only hides what a role cannot use. A member who types an owner-only address
(Team, Usage and Billing, Settings → Company, Advanced) sees the "You do not have access"
page; their own Profile stays open. The panel learns who is signed in from
`GET /api/auth/company/me/` and reads it again on every page change.

### Inviting team members

The owner invites colleagues from the Team page (`POST /api/company/team/invites/`; the same
path lists pending invitations, `…/<id>/resend/` sends a new link and `DELETE …/<id>/` revokes).
Only owners may use these routes (action `team.invite`). The link is a shared `LinkToken` with
the purpose `team_invite`, valid `tokens.team_invite_days` (7) days, random, single-use and
stored only as a hash; resending makes the older link stop working. The invitation itself
(`companies.Invitation`) keeps the email encrypted and refers to its tokens by a random number.

A company can have `team.max_accounts_per_company` (3) accounts including the owner. Seats are
the people who have not been removed plus invitations still open (pending and not expired); the
limit is checked again when an invitation is accepted. Inviting an address that already has an
account (in any company) or a pending invitation, or going over the limit, gives a clear
message (with the number allowed). Sending and resending share the limit of
`rate_limits.invites_per_hour` (20) per company.

The invitee opens `/accept-invite?token=…`, chooses a name and a password (the shared password
rules) and becomes a **member** with the email already verified; accepting counts as agreeing
to the Terms and Privacy Policy. Nobody is logged in by accepting; the page then offers to log
in. A visitor who is logged in as someone else is asked to log out first. A refused attempt
(weak password, address taken in the meantime, suspended company) does not use up the link.

### Admin login

Admins sign in at `/admin/login` (API `/api/auth/admin/login/`), apart from company users. Email,
password **and** an authenticator code are always needed: a right password only hands out a
short-lived signed step, and the session starts after the code. An admin with no authenticator
yet sets one up at that point. There is no public admin sign up and no recovery codes.

- **First super admin:** on the server run `python manage.py create_first_super_admin --name "…"
  --email …`. The password is typed at a hidden prompt (never an option) and follows the normal
  password rules. It works only while no admin exists at all; afterwards it refuses.
- **Sessions:** access token 10 minutes (`tokens.admin_access_minutes`), refresh 8 hours
  (`tokens.admin_refresh_hours`). Admin tokens use their own keys and are accepted only by admin
  routes (see "Security test suite").
- **Wrong guesses:** counted and paused like company logins (same limits), but separately from
  company ones, for passwords and for codes.
- **Lost device:** another super admin must reset the authenticator; the wrong-code message says
  so. The reset action is built with admin controls (BERA-093/094), after the audit log exists.

### Admin roles

`adminusers/role_matrix.py` is the one place that says what each admin role may do; a route names
an action (`require_action(request.user, "plan.change")`) and never lists roles. Support may view
companies, usage and jobs, block or unblock a team member, retry or cancel jobs, handle data
requests and read announcements. Everything else (plans, prices, AI, settings, limits,
subscriptions, admin users, Payments, the Audit log and Advanced) is super admin only: hidden in
the menu (`components/admin/navigation.ts`), shown "no access" if typed in, and refused by the
server (403) if requested directly. The role is read from the database on every request, so a
change applies at once. `adminusers/admin_accounts.py` (`change_role`, `set_status`) refuses to
demote, block or remove the last active super admin.

### Audit log

`audit/` keeps a permanent record of important actions: who (`actor_kind` and `actor_id`), what
(`kind`), when, which company or person, and the written reason where one is required. Every kind
is listed in `audit/events.py`; to log a new action, add its kind there and call
`audit.service.record(kind, actor=…, target=…, reason=…, details=…)` in the same transaction as
the change. The kinds marked "not built yet" there (member removed, project deleted, export,
retention change, plan change and the admin ones) must be recorded by the ticket that builds them.

- **Reason:** every admin action that changes another account or a company needs a written
  reason (`reason_required` in the list). Without it the action is refused and undone.
- **Permanent:** the app cannot update or delete an entry (model and queryset refuse), and a
  database trigger refuses it too, even for direct queries.
- **No secrets:** passwords, tokens, codes, email addresses and CV text are never recorded:
  `details` accepts only short plain values and refuses names that suggest a secret. A failed login
  names the account tried, never the typed address.
- Entries hold plain numbers, not links, so they outlive the accounts they are about. The viewer
  comes with the Audit log page.

### Security events and alerts

Security events are `security.*` kinds in the audit log: a used refresh token presented again,
a signed-in person refused an action their role may not do, a source blocked for too many
requests or wrong attempts (recorded once per block, not per request), and more than 200 CV
downloads by one user in an hour (`security.download_alert_threshold`; the CV download calls
`audit.security.watch_cv_downloads(user)`). Failed logins and admin actions are audit entries
already. Record a new security event with `audit.security.record_security_event`.

Every active super admin is emailed at their own address, at most once per kind per hour
(`security.alert_cooldown_minutes`). With no active super admin nothing is sent. To check that
alerts arrive: `python manage.py send_test_security_alert`.

### Company activity log

`activity/` keeps what a company's team did (uploads, stage changes, downloads, shares, invites,
removals, setting changes), for the Activity tab later. It is separate from project data and from
the admin audit log. Each entry holds who (their number and the name they had then, so it stays
readable after they are removed), what, when and the item concerned, never CV text, passwords or
addresses. Kinds are listed in `activity/events.py`; the ones marked "not built yet" must be
recorded by the ticket that builds them, with `activity.service.record(...)`.

- **Reading:** `GET /api/company/activity/`, owner only (`activity.view`), newest first, in pages
  (`activity.page_size`, continue with `?before=<next_before>`). It only ever shows the signed-in
  company's own entries.
- **Retention:** every company follows `retention.default_days` until companies can choose their
  own (Profile and company settings ticket). Older entries are not listed, and
  `activity.service.purge_expired_entries` deletes them; it still has to be scheduled as a
  periodic job.

### Team management

The Team page (owner only) lists the members (name, email, role, status; removed people are not
listed) above the pending invitations. API under `/api/company/team/`: `members/` (list),
`members/<id>/` (DELETE removes), `transfer-ownership/` (POST `member_id` and the owner's
`password`).

- **Removing:** the person's status becomes removed, which ends their sessions at once. Their
  work and their row stay with the company, and the activity log keeps their name. The owner can
  never be removed, so there is always exactly one owner; the owner hands the company over first.
- **Handing over:** needs the owner's password (wrong entries count toward the login pause),
  and only an active member of the same company can receive it. Both people's rights change
  immediately, with the tokens they already have.
- Both actions are written to the audit log and the company activity log.

### Admin limit and subscription controls

API only, under `/api/admin/` (`adminusers/control_urls.py`); the Companies pages come later. Every
route is super admin only (support gets 403), needs a written `reason` and is audited. A refused
request changes nothing and writes no entry.

- `POST companies/<id>/suspend/` and `unsuspend/`: suspending ends every session of the company (the
  shared revoke function); the company sees the suspended message at sign-in; the owner is emailed.
- `PUT companies/<id>/limits/<name>/` (`value`) and `DELETE` (clear): a company's own limit, any valid
  value, higher or lower; clearing returns to the plan's value. It applies at once. A value below
  current use blocks new work only; nothing is deleted.
- `POST companies/<id>/subscription/grant-free/` (`plan_id`, `period_end`), `end-free/` and
  `terminate/`: use the subscription state functions. Terminating ends access only; data is kept
  until the retention period ends. The owner is emailed by the state change.
- `POST admin-users/<id>/two-step/reset/`: another super admin clears an admin's authenticator and
  ends all their sessions; they enrol again at the next login. Never your own.
- `POST company-users/<id>/two-step/off/` (`identity_checked: true`, and a reason saying what was
  checked): turns it off, ends all their sessions, emails them.

- `POST company-users/<id>/block/` and `unblock/` (super admin and support, with a reason): blocking
  ends every session of that person at once, the owner is emailed and it is audited. The company
  owner can never be blocked (suspend the company instead). A blocked person's old tokens answer the
  same 401 as anyone not signed in; signing in with the right password shows "Your access has been
  blocked. Please contact your company owner or support." and a wrong password still gets the
  neutral failure. Unblocking restores access but not old sessions.

New email `account_notice` (suspension, restore, two-step off); limits and subscription changes use
`usage_notice`.

### Plan and usage display

`GET /api/company/usage/` (owner only, `billing.view`; members get 403) returns the company's plan
name and state, the current period dates, CVs used/limit/left (scored plus waiting, exactly what the
monthly limit check counts), tokens used against the cap, the estimated cost stored for the period,
projects used, a `warning` of 80 or 100 for CVs and for tokens (the percents come from the platform
setting `usage.warning_percents`) and `refresh_seconds` (`live_updates.max_delay_seconds`). It is
read only and shares its functions with the limit checks, so what is shown is what is enforced.
Projects used is 0 until projects exist (`plans/summary.py::projects_in_use`).

The company top bar shows the owner a small meter (CVs used of the limit) that re-reads on that
interval and opens a popup with the full figures and warnings in words. The full Usage tab and the
billing pages come in their own tickets.

### Limit enforcement

`plans/limits.py` answers whether one more thing fits the plan. Each check returns allowed or not,
a stable `code`, a plain message, the `prompt` to show (`upgrade`, or `renewal` on the highest plan
or when the subscription is expired) and how much room is left. `raise_if_blocked()` turns a
refusal into the shared error with the limit and prompt in its details. The server answers; the
Upgrade and renewal popups are built in their own ticket.

- **Reading limits:** always through `limit_for(company_id, name)`: a company's own `LimitOverride`
  (set later by the admin controls), else its plan's value, read fresh each time so a change applies
  at once. A company with no plan has no allowance (0), except team size, which keeps the platform
  setting `team.max_accounts_per_company` until a plan is chosen.
- **Checks:** `check_cvs_this_month` (scored this period plus waiting; a failed CV gives its
  allowance back), `check_cvs_per_project`, `check_projects`, `check_top_n`, `check_team_size`,
  `check_ai_allowed` (tokens in and out against the monthly cap; AI is paused until the next period
  or a limit increase). An expired subscription is refused by every check with the renewal prompt.
- **Batches:** `split_batch` accepts files in order up to the room left in the month and the
  project, and returns every other file with the code, message and prompt of the limit that ran out.
- **Wired now:** the team invite (send, resend, accept). The project, scoring-settings, upload and
  AI tickets call the other checks. A caller that accepts files must hold the company row lock while
  checking and recording, so parallel uploads cannot pass a limit together.

### Usage counting

`usage/service.py` counts what each company uses, per company, per project and per billing period.
Periods are monthly, starting on the subscription's start day (the sign-up day before any
subscription; short months use their last day), are stored and kept for ever. There is no route:
only the server's own work writes counters, so a company cannot change its own.

- `accept_cv` when a file is accepted: fixes the period the CV counts in and records it in a ledger
  (`CvUsage`). Calling it again for the same CV changes nothing. Rejected files and skipped
  duplicates never reach it.
- `mark_scored` when scoring succeeds: counts the CV once, in the period it was accepted in.
  Re-scoring returns False and adds nothing. `mark_failed` gives the allowance back (the CV is
  never counted). `waiting_cvs` counts accepted CVs still waiting, for the monthly limit.
- `add_tokens` (tokens in and out and the estimated cost, passed in by the AI usage tracking):
  work on a CV, re-scoring included, counts in the period the CV was accepted in, whenever the
  call ran. Work with no CV counts in the period now.
- `current_usage`, `usage_history`: totals and per-project figures. Reading creates nothing.
- Every change locks the company's row first, so parallel uploads are never double counted or
  missed.

### Subscription states

Each company has one `Subscription` (plan, state, period start and end, renewal on or off). States:
No plan (new company), Active, Past due, Cancelled (active until the period ends), Expired and
Granted free. All changes go through `plans/subscriptions.py` (`activate`, `mark_past_due`,
`cancel`, `expire`, `grant_free`, `end_free`); only payment events and admin actions call them and
there is no route, so a company cannot change its own state.

- **Access** (`can_view`, `can_create_project`, `can_upload`, `can_score`): No plan and Expired can
  view and download only; Active, Past due (with a warning), Cancelled and Granted free have full
  access. The upload, project and scoring tickets must call these helpers.
- **Dates:** the state in use (`effective_state`) is worked out from the dates, so access is right
  even if no job ran. Past due ends after `billing.past_due_grace_days`; a cancelled period, a free
  grant or an active period with renewal off ends at its end date. `expire_lapsed_subscriptions`
  saves, logs and emails those changes; it is not scheduled until periodic jobs exist.
- **Log and email:** every change is an audit entry (`subscription.state_changed`, or the admin free
  kinds with a required reason) and the owner is emailed. A free grant is refused while a
  subscription still gives access, so a company never holds two.

### Regional pricing

`GET /api/plans/` (public) lists the active plans in display order, never hidden or archived ones,
with the price for the visitor's detected country. `plans/pricing.py::price_for(plan, country)` is
the one rule: Pakistan sees the PKR price when set, otherwise USD with a note; every other or
unknown country sees USD. Billing, upgrade and renewal pop-ups and plan display for a signed-in
company must call it with the company's locked country. A company's country is set at sign up and
no route changes it (support only).

### Plans management

Super admins manage the subscription plans under `/api/admin/plans/` (list and create; read,
`PATCH` and `DELETE` on `<id>/`). API only; the Admin Plans and Pricing pages and the public
pricing route (which needs the visitor's country) come with later tickets.

- **Fields:** name, short description, USD price per month, optional PKR price, CVs per month, CVs
  per project, maximum projects, maximum team accounts (including the owner), maximum top-N,
  monthly AI token cap, status (active, hidden, archived) and display order. Plans are monthly; no
  rollover. Limits are positive whole numbers; prices are positive with two decimals.
- **Starting plans** (data migration, hidden): Starter 250 CVs / 3,000 PKR, Growth 500 CVs /
  5,000 PKR, Scale 7,000 PKR. The USD prices, the Scale CV count and the other limits are set by the
  owner. A plan cannot be active until every number except the PKR price is filled in.
- **Subscribers:** price and limit changes never reach current subscribers silently. They wait as
  a pending change until renewal (`plans.service.apply_pending_change`, for the Subscription
  states ticket to call) unless the edit says `"apply": "now"`. Name, description, order and
  status apply at once. `plans/subscribers.py` (`subscriber_count`) returns 0 until subscriptions
  exist. A plan with subscribers can be archived but not deleted.
- **Pricing page:** `plans.service.active_plans()` returns only active plans, in display order.
- **Audit:** create, change and delete are written with the old and new values; a change or delete
  needs a written reason. Only super admins can do any of it.

### Company data isolation

A company can only reach its own data: through `core/scoping.py`, lists, searches, single
records, downloads and updates all start from the signed-in person's company, and a record of
another company gives exactly the answer for a record that does not exist. The isolation tests
(`signin/tests/test_company_isolation.py`) try to reach another company's data for every kind
the ticket names (projects, CVs, results, users, files, usage, invoices, exports, shared
reports), by detail, list, live updates, search, download or export link, change, delete,
company parameters in the address, other kinds' identifiers, forged and moved sessions, and as
a visitor or an admin. They use stand-in kinds until the real features exist. **When a new kind
of company data is added**, its model must be built on `CompanyOwnedModel`, and a test fails
until its name is listed in `REAL_MODELS_WITH_ISOLATION_TESTS` there, next to isolation tests
for it. Run them alone, for example before launch, with:

```
python -m pytest -m isolation
```

### Security test suite

The tests that protect the security rules are listed by area in
`server/core/tests/security_suite.py` and carry the `security` marker: sign-in, tokens
(tampered, unsigned, expired, reused, wrong audience), permissions per role, wrong-company
access for every kind of object, hostile input, rate limits, and blocked or suspended people.
`core/tests/test_security_every_route.py` walks every protected route of the server and
attacks it in all of those ways, so a new route is covered the day it is added.

They run with the normal `python -m pytest`, so a failing security test fails the change.
`python -m pytest -m security` runs them alone, and CI shows them as their own check, "Security
tests". To make that check block merging, require "Security tests" (with the other checks) in
the repository's branch protection settings on GitHub; that setting lives on GitHub, not in
the code. **Keep extending it**: when a feature adds a route, a role, a kind of company data
or a limit, its security tests go into one of the areas above (or a new area is added there);
`core/tests/test_security_suite.py` checks that every area and file is present.

### Database accounts and protected data

Three database accounts exist, locally too: the app (rows only, cannot change the structure), the
migrator (`migrate`) and backups (read only). `scripts/dev.py` creates them; staging and
production use `python manage.py provision_database_roles`. See
[docs/security/database.md](docs/security/database.md), which also shows how to store a field
encrypted and still find it by a hash. If you have a local database from before this change, run
`python scripts/dev.py reset-db` once (with Docker also `docker compose down -v` first).

## Create project

`POST /api/company/projects/` (`server/projects/`) creates a project for the signed-in user's own
company; the company is never read from the request. Owners and members may both create.

- Fields: `title` (required, up to 120 characters) and `job_description` (required, up to 15,000,
  pasted text), plus `acknowledge_warnings`. The limits are the platform settings
  `projects.title_max_length` and `projects.description_max_length`. The optional PDF/DOCX file
  comes with the Text reading from files ticket; this one takes pasted text only.
- The project limit uses `plans.limits.check_projects` while the company row is locked, so two
  creations at once cannot pass it together. A reached limit answers 409 `project_limit_reached`
  with `details.prompt` (`upgrade` or `renewal`), and the form opens the matching popup.
- Warnings never refuse a project: a description under `projects.short_description_length` (300)
  characters, and a title the company already uses (case ignored). Without
  `acknowledge_warnings: true` the server answers 409 `project_warnings` with the list in
  `details.warnings`; the form shows them in a popup and "Create anyway" sends it again confirmed.
- The reading model and prompt version (`ai.reading_model`, `ai.prompt_version`, seeded stand-in
  values until Model settings and Prompt versions exist) are copied onto the project when it is
  created and never change after. Showing them to admins comes with the Companies detail ticket.
- The plan meter's project count now counts real projects.

## Projects list

`GET /api/company/projects/` returns the signed-in user's own company's projects (owners and
members), one page at a time. The company is never read from the request.

- Query: `search` (part of the title, case ignored), `status` (`active` default, `archived`,
  `all`), `sort` (`updated` newest first default, `title`, `best_score` highest first, projects
  without a score last) and `page` (from 1). Unknown fields or values answer 400; a page past
  the end is an empty list.
- Page size is the platform setting `projects.page_size` (20). The answer has `results`, `page`,
  `page_size`, `total` and `pages`.
- Each row: `id`, `title`, `cv_count`, `best_score`, `status`, `updated_at`. CV count (0) and
  best score (empty) come from `projects/listing.py::with_figures`, the one place to change when
  the Candidate record ticket adds candidates.
- Projects now have a `status` (`active` or `archived`; archiving itself is a later ticket) and
  an `updated_at` that moves on every save.
- The Projects page shows the list with search, sort and filter controls, and Previous / Next
  when there is more than one page.

## Edit, archive and delete project

Routes under `/api/company/projects/<id>/` (own company only; another company's project is
"not found"): `GET` (reading), `PATCH` (edit title and/or job description, same limits as
creating; the pinned model and prompt version never change), `POST archive/`, `POST restore/` and
`DELETE` (owner only, body `{"confirm_title": "<exact title>"}`). Owners and members may edit,
archive and restore. The Settings tab of the project page has these actions.

- **Archived** is read-only and reversible. `projects.service.require_editable(project)` refuses
  with 409 `project_archived`; every later ticket that edits a project or accepts uploads must
  call it first (downloads do not). Archived projects do not count toward the project limit
  (`active_project_count`), so restoring one is checked against the limit again and can answer
  `project_limit_reached` with the Upgrade prompt. Past usage stays in the usage history.
- **Delete** goes through `projects/deletion.py::delete_project` in one transaction: running work
  is stopped first (`register_work_stopper`), then each kind of project data is removed
  (`register_project_data`, which also removes files from storage), then the project. If any step
  fails nothing is deleted. **Every ticket that stores project data (files, candidates, scores)
  must register it there and add its name to `EXPECTED_REGISTRATIONS` in
  `projects/tests/test_project_deletion.py`**; a guard test fails for any model that points at a
  project and is neither registered nor kept on purpose (the usage ledger).
- Deletion is logged in the company's activity log as `project_deleted` with the project's
  identifier only: no title and no names.

## Requirement extraction and the shared AI call

**The one AI call.** `ai/client.py::call_ai(company_id, model=, instructions=, text=, project_id=,
cv_id=, estimated_cost=)` is the only way the app reaches the AI provider (a test fails if another
file imports it). It uses the official `openai` library, the key `OPENAI_API_KEY` (required in
staging and production, held by the app only; without it every call reports "unavailable" and
screens fall back to manual entry), the platform timeout `ai.request_timeout_seconds` and output
size `ai.default_max_output_tokens`, and records the answer's tokens with
`usage.add_tokens`, so they count toward the company's token usage and never as a CV. Cost is
passed in by the AI usage tracking ticket (zero until then). Nothing sent or received is logged.
Model settings, Prompt versions and AI usage tracking extend this function; do not add another.

**Suggesting requirements.** `POST /api/company/projects/<id>/requirements/suggest/` (own
company; archived projects are refused) asks the AI for must-have and nice-to-have requirements
using the project's pinned model and the stand-in prompt `ai.requirement_extraction_prompt`
(Prompt versions will supply prompts by the pinned version). Nothing is saved: the Requirement
editor lets the person edit and confirm. Before the call `check_ai_allowed` applies the monthly
token cap (409 with the Upgrade prompt).

- The answer is untrusted: entries with an unknown kind, no text, more than
  `requirements.max_length` (120) characters or repeating another are dropped, and at most
  `requirements.max_total` (30) are kept, with a `trimmed` warning when more were given.
- AI unavailable or nothing usable: HTTP 200 with `fallback: true` and a friendly `message`
  inviting manual entry; tokens already spent are still counted.
- Warnings: `short_description` (under `projects.short_description_length`, few requirements
  expected) and `other_language` (the AI reports a language other than English; the requirements
  are written in the description's language).
- The Requirements tab has a "Suggest requirements" button showing the proposal read-only.

## Requirement editor

`GET` and `PUT /api/company/projects/<id>/requirements/` (own company; owners and members). The
whole list is sent and replaces the stored one, so order, weights and removals can never
disagree. Each requirement has a `kind` (`must` or `nice`), `text` (up to `requirements.max_length`,
120) and a `weight` from 1 to `requirements.weight_max` (5, default `requirements.weight_default`,
3); at most `requirements.max_total` (30) per project. Sending an `id` keeps an existing one.
An archived project is read-only (409 `project_archived`).

- **Near-duplicates** (same words, or at least `requirements.near_duplicate_percent` similar)
  come back as `near_duplicate` warnings on read and save; they never block saving.
- **Re-scoring notice.** A change that affects scoring (kind, wording or weight, not order) when
  CVs were already scored answers 409 `rescoring_needed` with `details.cvs` and
  `details.estimated_cost`; the editor shows them in a popup and "Save changes" sends the list
  again with `acknowledge_rescoring: true`. The numbers come from
  `projects/rescoring.py::rescoring_estimate`, which the Re-scoring ticket fills in (nothing is
  scored yet, so it reports zero).
- **Before scoring.** Scoring tickets call `requirements.require_requirements_for_scoring(project)`:
  409 `requirements_needed` when the project has none.
- Requirements are removed with their project (registered in `projects/deletion.py`). The
  suggestions from the AI can be added to the editor with "Add to requirements" and are saved
  only when the person saves.

## Project scoring settings

`GET` and `PUT /api/company/projects/<id>/scoring/` (own company; owners and members). `PUT`
sends every value: `must_weight_percent` and `nice_weight_percent` (always totalling 100;
default 70/30), `recommendation_threshold` (0 to 100; default 75) and `top_n` (default 10).
`GET` also returns `top_n_cap`, the plan's limit. The panel is on the project's Settings tab.

- **Defaults.** A project with no saved row follows `projects/scoring_settings.py::
  scoring_defaults()`, today the platform settings `scoring.must_have_weight_percent`,
  `scoring.nice_to_have_weight_percent`, `scoring.strong_match_min` and `scoring.top_n`; the
  company's own scoring defaults plug in there. Saving stores the project's own values.
- **Plan cap.** `top_n` is checked with `plans.limits.check_top_n` (409 `top_n_limit_exceeded`
  with the Upgrade prompt, Renewal when the subscription has ended) and shown never above the
  cap, even if the plan was lowered after saving.
- **Impossible combinations** answer 400 with a message per field: weights not adding to 100 or
  outside 0 to 100, a threshold outside 0 to 100, a top list under 1. The database refuses
  weights that do not total 100 as well.
- **Recalculation.** Saving a change calls `projects/recalculation.py::recalculate_scores`, which
  never uses the AI (the per-requirement results are kept and only recombined). The Score
  calculation ticket fills it in; today it has nothing to recalculate and reports 0. An archived
  project's settings cannot be changed. The extra-factors choice comes with the Extra scoring
  factors ticket.
- Settings are removed with their project (registered in `projects/deletion.py`).

## Bulk CV upload

`POST /api/company/projects/<id>/cvs/` (multipart, field `files`; own company, owners and
members) takes CVs for a project, and `GET` on the same address returns what the upload area
checks first (`allowed_types`, `max_file_size_mb`, `max_files_per_batch`, all platform
settings `uploads.*`). The answer has one result per file, in order: `accepted`, or `rejected`
with a `code`, a plain `message` and, for a plan limit, the `prompt` (upgrade or renewal). Good
files go through while bad ones get their own message. The upload area on the project's Overview
tab sends each file in its own request, so it shows per-file progress and, after a dropped
connection, "Try again" re-sends only the failed file.

- **Order of checks per file:** too many files in the request (`too_many_files`), type
  (`wrong_type`), empty, size (`too_large`), then the content (`damaged`, `password_protected`).
  Then, with the company row locked, `plans.limits.split_batch` applies the monthly and
  per-project CV limits (`monthly_cv_limit_reached`, `project_cv_limit_reached`, or
  `subscription_expired`), and each accepted file goes through `usage.accept_cv`. The upload
  rate limit (`rate_limits.upload_files_per_10_minutes`, 100) counts every file. An archived
  project takes no uploads (409 `project_archived`).
- Files are kept by the private file storage (see Private file storage). The file check is
  `cvs/file_checks.py::check_cv_file` (see File checks).
- Accepted files are `CvFile` records with status `waiting`; Background processing takes them from
  there. The cost estimate is shown once Cost estimate before processing exists.
- Deleting a project removes its files from storage and their records (registered in
  `projects/deletion.py`); the usage history stays.

## File checks

`cvs/file_checks.py::check_cv_file(name, data)` is the one check every uploaded CV goes through
(the upload calls it and nothing else; no route, no page). It returns a `FileCheck`: a `problem`
(`code` and plain `message`) or, for an accepted file, its `file_type`, `page_count` and a
`notice`.

- **Real type from content.** The type is decided from the bytes, not the name: a PDF must
  carry the PDF signature, a Word file must be a zip with its main part. A renamed file, or one
  that is not a PDF or Word file at all, is refused as `type_mismatch`; an old `.doc` is not
  accepted. Name, empty and size (`uploads.max_file_size_mb`) are checked before the file is read.
- **Unreadable and protected.** `damaged` (cut off, garbage, missing parts), `password_protected`
  (encrypted PDF; encrypted Word file) and `scanned_image` (a PDF with no text on the pages
  read: "This looks like a scanned image. Please upload a text-based PDF or a Word file.").
- **Macros, scripts and embedded content** are refused as `active_content`: Word macros and
  macro-enabled types, embedded objects and ActiveX; PDF JavaScript, launch and form-submit
  actions, document or page actions, XFA forms, attached files and media. Files are only read as
  data (pypdf for PDFs, the standard zip reader for Word); nothing is run, and a test fails if
  the checks ever call a program or `eval`.
- **Unpacking is limited.** A Word archive is measured from its headers first and refused unopened
  above `uploads.max_unpacked_mb` (100) or `uploads.max_archive_entries` (2000); a PDF's
  compressed parts are held to the same size while it is read.
- **Pages.** The first `uploads.cv_pages_read` (15) pages are read; a longer CV is accepted with a
  `notice` ("This CV has 22 pages. Only the first 15 are read."), shown beside the file in the
  upload area. The page count is kept on the `CvFile`. A Word file's count is the one its
  properties state (none if it states none).
- **File names** are cleaned for display (`core.validation.safe_file_name`) and are never part
  of a storage path (keys are made from ids).

## Private file storage

`privatefiles/` is the one place files are saved, read, removed and linked (`save_file`,
`read_file`, `delete_file`, `download_link`); nothing else knows which store is behind it. Keys
are built from server-made ids only (`cvs/<company>/<cv>`), never from a file name.

- **Where.** Development and tests: a private folder (`PRIVATE_FILES_ROOT`, default
  `local_storage/`; folders `0700`, files `0600`; no route serves it). Staging and production:
  a private Cloudflare R2 bucket through its S3-compatible interface (`boto3`), no public
  address. R2 encrypts every object at rest, so nothing extra is asked of it. Production needs
  `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` and `R2_BUCKET` (app only; the
  app refuses to start without them; see `.env.example`).
- **Short-lived links.** `download_link(key, file_name)` returns `{url, expires_at}`: a signed R2
  address, or in development a signed `/api/files/<token>/` link that `read_for_link(token)`
  reads back (refusing a changed or expired one with 403 `link_invalid`). Links last
  `storage.download_link_hours` (24). **A link is made only after a permission check:**
  `cvs/downloads.py::download_link_for_cv(user, cv_id)` requires a company user whose role may
  download and whose company owns the CV (anything else is "not found" or "not allowed");
  archived projects can still be downloaded from. The download route and buttons come with the
  Downloads ticket, which must call that function (and `audit.security.watch_cv_downloads`).
- **Storage failures.** A failed attempt is tried again after the waits in
  `storage.retry_waits_seconds` (1 and 3 seconds); then `StorageUnavailable` (503
  `storage_unavailable`) is raised. In an upload that file is reported `failed` (`storage_failed`:
  "This file could not be saved. Please try again."), the rest go on, and the upload area offers
  "Try again" for that file. Files are saved before the company lock is taken, and files that
  turn out not to be kept (over a limit, or an error) are removed again.
- **Deletion.** `cvs/service.py::remove_cv_file(cv_file)` removes the stored file and then the
  record; deleting a project does this for all its CVs, and **the candidate-deletion ticket must
  call it for the candidate's CV**. If the store cannot delete, nothing is deleted and the person
  is told to try again.
- Connects to Retention settings (which will call `remove_cv_file` when files expire) and Daily
  backups (the bucket and the database are backed up together).

## Duplicate detection

Two checks in `cvs/duplicates.py`; no route and no page (the review flag is shown later in
Candidate detail and the Ranked candidate list).

- **Identical file, at upload.** `split_identical` compares a SHA-256 of the file's bytes with the
  project's other CVs and with earlier files of the same upload, under the company lock. A repeat
  gets the result `skipped` (`duplicate_file`: "This file is already in the project, so it was
  skipped."), is not stored and never counted, and does not use the monthly or project limit.
  The name does not matter; another project or company is never compared. The database allows
  one copy of a file per project.
- **Likely same person, after reading.** `review_likely_duplicate(cv_file, text)` is called by
  processing with the CV's text. It finds emails and phone numbers (`contact_hashes_in`; phones
  compare their last `duplicates.phone_digits`, 9, digits, so `+44 7700 900123` equals
  `07700-900-123`) and keeps only keyed hashes of them (`CvFile.contact_hashes`), never the
  values. When another CV of the project shares one, this CV is marked `review = flagged`
  with `duplicate_of`.
- **Deciding.** A flagged CV stays marked until the person decides: `keep_flagged_cv` (it stays
  and counts) or `discard_flagged_cv` (the file and record are removed and its allowance is
  given back with `usage.mark_failed`). A CV already kept is never flagged again. Both refuse a
  CV that is not flagged and an archived project.
- **Counting.** `counts_toward_limits(cv_file)` is false while a CV is flagged. **The scoring
  pipeline (Background processing) must call `usage.mark_scored` only when it is true, and count
  a scored CV when it is kept.** Until then a flagged CV waits like any other.

## Text reading from files

`cvs/text_reading.py::read_text(file_type, data, max_characters=None)` is the one function that
turns a PDF or Word file into text; Background processing calls it after File checks accepted the
file (no route and no page for CVs). It returns `CvText(text, trimmed)`.

- **Reading order.** PDFs are read with pdfminer.six's layout analysis, so a two-column page
  reads one column after the other, for the first `uploads.cv_pages_read` (15) pages. The PDF
  reader runs in its own limited process (`cvs/pdf_worker.py`: memory limit
  `reading.worker_memory_mb`, time limit `reading.worker_timeout_seconds`, empty environment), so
  a hostile PDF can at worst kill that process and the file is reported as unreadable. Word files
  are read with python-docx in document order: headings as their own lines, list items as
  `- item`, tables row by row (`a | b`, merged cells once), the page header (contact details are
  often there) first, and text boxes last (their fallback copy skipped).
- **Cleaning.** One form for every language and script: composed characters (NFKC, so ligatures
  and fullwidth forms become ordinary), no invisible, bidirectional or control characters, odd
  spaces made ordinary, `(cid:N)` placeholders from fonts without a text map removed, tidy blank
  lines.
- **Trimming.** Text over `reading.max_characters` (40,000) is cut at a word boundary where it
  can (never between a letter and its accent) and `trimmed` is true so the caller can flag it.
- **Failures.** Text with fewer than `reading.min_characters` (30) letters and digits, or a file
  the readers cannot open, raises `CvTextUnreadable` (HTTP 422 `cv_unreadable`: "We could not
  read this file."). **The caller must not count that CV: processing calls
  `usage.mark_failed(company_id, cv_id)`.**
- **Job description file.** `POST /api/company/projects/read-description/` (multipart `files`,
  one file; the Create project form's optional file) runs File checks, then `read_text` (cut to
  `projects.description_max_length`), and returns `{text, trimmed, notice}` for the description
  box. The file is never stored and nothing is counted; it uses the upload allowance. Problems
  come back as a `file` field message.

## Background processing

`cvs/processing.py`. Accepted CVs are processed in the background (Django-Q workers), so people
can leave the page. Statuses: `waiting`, `reading`, `scoring`, `done`, `failed` (and `cancelled`).

- **The queue is the database.** A CV is a `CvFile` row; a restart loses nothing. Workers are woken
  by a task per accepted file (`processing.tick`), and a sweep scheduled **once a minute**
  (`processing.sweep`) wakes them for anything waiting, which covers work whose task was lost.
  The schedules (this one, and the once-a-day `core.periodic.purge_rate_limit_counters`, which
  clears old rate limit counters) are created by migrations, so every deployment has them.
- **Nothing runs twice.** A worker claims a CV atomically with a fresh `claim_token` (rows another
  worker holds are skipped); only the token's holder can change the CV, so a worker replaced after a
  timeout or restart can neither run its steps nor overwrite the new worker.
- **Fair.** Each claim goes to the company that waited longest for a turn (`ProcessingTurn`), then
  to its oldest CV, one CV per task, so a large batch cannot hold up other companies.
- **Retries.** A step that fails with an unexpected error is tried again after
  `processing.retry_waits_seconds` (30 s, then 120 s) up to `processing.max_attempts` (3) tries,
  then the CV is `failed` with a plain reason ("We could not process this file after several tries.
  You can retry it."). A CV stuck in one try longer than `processing.stuck_minutes` (5) is taken
  from its worker by the sweep and counts as a failed try. A file that can never work
  (`PermanentFailure`, such as no readable text) fails at once. Error messages and CV text are never
  logged or shown; only the kind of error is logged.
- **Counting.** A failed or cancelled CV is not counted (`usage.mark_failed`); Retry
  (`POST /api/company/projects/<id>/cvs/<cv>/retry/`) counts it again, so the month's limit is
  checked (409 with the Upgrade prompt when full; archived projects refuse). Done does not itself
  count a CV: the scoring step calls `usage.mark_scored` (only when
  `duplicates.counts_toward_limits` is true).
- **Cancel.** `POST /api/company/projects/<id>/cvs/cancel/` (optionally `{"batch": id}`; the upload
  area gives everything dropped together one batch id) skips every CV that has not started and
  gives its allowance back; running ones finish.
- **The project page.** `GET /api/company/projects/<id>/processing/` returns a count per status
  and each CV with its status, reason and `can_retry`, plus `refresh_seconds`
  (`live_updates.max_delay_seconds`) for how often the page looks again; Live updates will replace the
  polling. The Overview tab shows it under the upload area.
- **Deleting a project** stops its processing first (registered stopper `CvProcessing`): unfinished
  CVs lose their claim, so a worker still busy with one changes nothing.
- **Steps plug into named slots**, in order: `text_reading`, `ai_reading`, `fairness_guard`,
  `scoring`. A slot with no step is skipped. A ticket adds its step with
  `processing.register_step(slot, function)`; the function gets a `StepContext` (the CV, its
  company and project, and a `state` dict that carries results to later steps of the same try). Add
  the slot to `EXPECTED_STEPS` in `cvs/tests/test_processing.py` with your test. Plugged in so far:
  `text_reading` (`cvs/steps.py`: reads the text, then looks for a CV of the same person).

## AI reading of CVs

The `ai_reading` step (`cvs/profile_reading.py`) turns the CV text into a profile once and
reuses it. It uses the shared `call_ai` function, so its tokens are counted for the CV and its
period by the Usage counting functions.

- The profile (`CvProfile`) holds skills, job titles with start and end dates, years of
  experience, education, certifications, languages and a short summary. It is saved with the
  reading model and prompt version pinned to the project.
- A CV with a profile is never read again: a retry after a later failure, and every
  re-scoring, use the saved profile and cost no tokens.
- An answer that is not valid JSON of the expected shape, or has no skills and no job titles,
  is asked for once more (`ai.invalid_answer_retries`). After that the CV fails with a clear
  reason and is not counted. An unavailable AI is retried by Background processing; a company
  over its monthly token cap fails with a reason and can be retried later.
- Every fact is checked against the CV text (`cvs/profile_checks.py`): skills, titles, degrees,
  institutions, certifications and languages that are not found are removed, and so is a date
  whose year is not in the CV. Years of experience are counted from the checked job dates (the
  figure the AI gives is ignored). Fields the AI adds beyond the ones above are dropped.
- Contact details (name, email, phone, address) are kept in their own table (`CvContact`),
  only when found in the CV. Entries holding a contact detail are removed from the profile, and
  so is a summary that contains one. Nothing from a CV or an AI answer is logged. Encryption
  and masking of that table come with Candidate data protection.
- Platform settings: `ai.cv_reading_prompt` (a stand-in until Prompt versions),
  `ai.cv_reading_max_output_tokens`, `ai.invalid_answer_retries`, `profile.max_items`,
  `profile.item_max_length`, `profile.summary_max_length`.
- Tests use a stubbed AI (`cvs/tests/test_ai_reading.py`).

## Fairness guard

`cvs/fairness.py::remove_personal_details(text, contact)` is the one function applied to CV text
before scoring (Requirement evaluation must call it). There is no route and no page. The
`fairness_guard` step runs it in the pipeline and keeps the result in `scoring_text`; scoring
never reads the original `text`. It makes no AI call.

- Removed wherever they sit (header, footer, table, middle of a sentence): the CV's own saved
  name, address, email and phone (`CvContact`); the value after a label such as Name, Photo,
  Age, Date of birth, Gender, Marital status, Nationality, Religion or Address (also a value on
  the next line, and "Age 34" or "DOB 12.05.1990" without a colon); a date after "born"; any
  email address or phone number. Ranges of years such as "2014 - 2017" are kept.
- Email and phone are kept only for the recruiter's view (in `CvContact`).
- Unlabelled words (a nationality, a religion, "married") are left alone on purpose, so real text
  such as "Indian cuisine" is not cut. Photos are images, not part of the text.
- Platform settings: `fairness.labels`, `fairness.born_words`, `fairness.min_name_part_length`,
  `fairness.phone_min_digits`.
- Tests: `cvs/tests/test_fairness_guard.py` runs a set of sample CVs and checks that none of
  their personal details remain while the work history does.

## Candidate record

When a CV has been read, the `candidate_record` step (`cvs/candidates.py`) creates its
`Candidate`. The slot sits between `fairness_guard` and `scoring` in the pipeline, so the record
exists before scoring and stays visible if scoring fails.

- A candidate links its project, its original file (`CvFile`), its profile (`CvProfile`) and its
  contact details (`CvContact`), and has a stage that starts as `new`. Other stages come with the
  Stages and notes ticket. Scores and notes (later tickets) point at the candidate with a
  cascading link.
- One candidate per CV: a retry finds the existing record.
- A CV that fails has no candidate. It stays in the project's file list from Background
  processing, as a failed item with its reason and a Retry button.
- `remove_candidate` removes the file from storage, the CV record, the profile, the contact
  details and (by cascade) everything linked to the candidate; the usage history stays. Deleting a
  project removes all its candidates the same way (registered in `projects/deletion.py`).
- The ranked list and the detail screen come with their own tickets.

## Candidate data protection

Everything about candidates is sensitive personal data. The rules are built into the shared layer
(`core/personal_data.py`, `core/protected_fields.py`, `core/logging_setup.py`) so later tickets
use them instead of writing their own.

- **Encrypted at rest:** the four contact fields of `CvContact` (name, email, phone, address) are
  `EncryptedTextField`s (AES-GCM, one purpose per column, key from `FIELD_ENCRYPTION_KEY`). The
  migration `cvs/migrations/0008` encrypts existing rows. The profile stays in plain fields: it
  holds no personal details after the fairness guard and is searched and ranked. Files stay in
  private storage; connections use TLS.
- **Masking:** `mask_email`, `mask_phone` (last four digits), `mask_name` (initials),
  `mask_address` (never shown) and `mask_contact`. Show a detail in full only where a person
  really needs it.
- **Logs:** candidate data is never given to a logger (a test reads the logger calls of the CV
  code and runs the pipeline with logging switched on). The log formatter scrubs emails, phone
  numbers and keys such as `phone`, `address` and `contact` as a second layer.
- **Emails and analytics:** no email template takes a candidate value, the email code never
  imports candidate models, and the pipeline sends nothing.
- **Admin and support:** `CandidateDataOnly` and the `CandidateDataView` base refuse every
  non-company sign-in with `candidate_data_blocked`; the CV views use it. Support tools use
  `cvs/support_figures.py`, which returns counts per status only. A test walks every admin route
  and the audit log and activity list and finds no candidate content; `assert_clean` in
  `cvs/tests/test_candidate_data_protection.py` is the check for later admin screens and exports.
- **Exceptions:** none are built. The audit kind `admin.candidate_data_exception` (written reason
  required) is reserved; an exception would be its own ticket and must be explicit, time limited,
  justified in writing and audited.
- Retention and deletion features are separate tickets.

## Library checks and updates

`python scripts/check_vulnerabilities.py` checks the server (pip-audit) and web (npm audit)
libraries against the public advisory databases. It runs on every change and every Monday
(`.github/workflows/vulnerabilities.yml`). A high or critical finding in a production library
fails the check; findings in development tools only warn. A risk we accept is written in
`security/accepted-vulnerabilities.toml` with a reason and a review date; once the date passes
the check fails until someone looks again.

Updating routine (weekly, after the Monday check):

1. Read the check's output. Fix serious findings first.
2. Patch and minor updates: `pip install -U <package>` (then update the range in
   `server/requirements.txt`) or `npm update` in `web/`; run all tests (`python scripts/dev.py test`).
3. Major updates (a library's next big version) get their own ticket, since they can break things.
4. If a fix does not exist or cannot be done now, accept the finding in writing with a review
   date no more than about three months ahead, and say who will look at it.
5. Commit lock files with the update so everyone builds from the same versions.

The tests that prove a known-bad library fails the check need internet access. Offline, run
`python -m pytest -m "not network"`.
