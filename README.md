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
