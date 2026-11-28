# T25 to T28: Project detail pages (company panel)

Source: owner's review of the project detail screens (Overview, Candidates, Compare,
Requirements, Settings). Target: UI first. Split into four tickets so each is small and tested;
T25 is built first. Whole suite runs after T27 (5-ticket cycle: T23, T24, T25, T26, T27).

## Root causes found (so the same fault is fixed everywhere, not only here)

1. **Uneven buttons.** `.page-actions` is a flex row with the default `align-items: stretch`, so
   any button next to a labelled field (a `Select` with a label above it) is stretched to the
   field's height (disabled Compare / Download selected / Change stage, Up / Down / Remove,
   Previous / Next page). Fix once in the shared styles, not per page.
2. **Toolbar with no structure.** Filters, a plain `Matrix` text link, Share report, Shared
   links, Upload CVs, Download, then a second row of bulk buttons, all in one wrapping row with
   mixed button kinds.
3. **Pagination text** sits on the text baseline of tall buttons, so it looks off-centre.
4. **Bulk-selection UI always on screen** (checkbox column, bulk buttons, "Move selected to")
   even when nothing is selected.

## Audit (part of every ticket)

Search the whole company panel and admin panel for the same patterns and fix them in the same
change: `page-actions` rows containing a labelled `Select`/`Input`; pagination blocks; rows of
`Button`s with mixed `variant`s; always-visible checkbox columns; native `<input type="file">`
styling; duplicated actions (e.g. "New project" in the top bar and on the page). List every
place found in the ticket report, and add a test or a CSS rule in `design-rules.test.ts` where a
rule can be checked automatically.

---

## T25: Overview layout, toolbars, buttons, pagination, selection

**Overview tab**
- Rearrange the cards (Funnel, Score distribution, Ranking, Requirement coverage) into one grid
  that fits a normal desktop screen without scrolling: 2 columns by 2 rows at wide screens,
  1 column on a phone. Requirement coverage becomes a compact card (internal scroll if many
  requirements, never a taller page).
- Cards of equal height per row; headings smaller than page headings.

**Candidates tab**
- One toolbar, left to right: `Filters` (secondary), then on the right `Share report`,
  `Shared links` (secondary), `Download` (secondary menu), `Upload CVs` (primary, the only
  filled button). All the same height, aligned on one centre line.
- Remove the `Matrix` link (the Compare tab shows the same thing; the Compare button remains).
- Checkboxes appear only after the person presses `Select`. In select mode a bulk bar replaces
  the toolbar's right side: `n selected`, Compare, Download selected, "Move to" stage menu with
  Apply, and Cancel. With nothing selected the bulk bar says nothing and its buttons are absent
  (not disabled grey blocks).
- Pagination: Previous, "Page x of y, n candidates", Next in one aligned row, same height,
  text centred vertically; hidden when there is only one page.

**Requirements tab (layout only in T25)**
- Up / Down / Remove become compact icon-sized buttons of the same height as the fields, in one
  row with the fields, labels aligned. Weight stays a select.

**Shared**
- `.page-actions` gets `align-items: center` (and a `--end`/`--between` modifier); buttons never
  stretch. Add the rule to the design page and to the audit.
- File input gets the shared field look (New project form and CV upload).
- `/design` shows toolbar, bulk bar and pagination samples.

Edge cases: 0 candidates (toolbar still aligned, no Select button); 1 page; 100 selected and the
compare limit (message stays, button hides the extra explanation in a popup); phone width (the
toolbar wraps into two clean rows, never a ragged one); keyboard use of Select mode; reduced
motion.

## T26: Matrix with many requirements

- The Compare matrix scrolls sideways inside its card; the Rank, Candidate and AI score columns
  are sticky on the left, the header row is sticky on top.
- A `Columns` menu (checkbox list) lets the person choose which requirements are shown; the
  choice is kept per project in the browser, with `Select all` and `Reset`.
- Requirement column headers are fixed width with the full text on hover/focus.
- Edge cases: 1 requirement; 40 requirements; no requirements chosen (message, keep at least
  one); long names; phone width; sort stays correct; the filter query is kept.

## T27: Requirements from the job description, with weights

- When a project is created, the server reads the job description and drafts the requirements
  (Must / Nice, text and a **weight** each) and saves them as the project's list, marked as a
  draft until the person has opened the Requirements tab and saved or confirmed it.
- The `suggest` endpoint also returns a weight for each requirement (new field on the answer,
  validated to the allowed range), and the prompt version is bumped.
- Requirements tab: the person can add, remove, reorder and edit text, kind and weight by hand;
  `Re-read job description` replaces the draft after a confirmation popup.
- Uses the existing billing/limit prompts and AI-outage fallback; errors via the shared error
  helper; no job description text or CV content in logs.
- Edge cases: AI unavailable (project still created, empty list and a plain notice); JD
  with no clear requirements; too many requirements (cap from a platform setting); duplicates;
  weights out of range; re-read after the person edited by hand; scoring is not started until
  the list is confirmed.

## T28: Project settings: more owner controls

Today the tab has title, job description, scoring weights, factors, archive and delete.
Approved by the owner: **JD file replace/download** and **Duplicate project**. The owner asked
for 10 to 15 more; the list below is a proposal and nothing beyond the first two is built
until each is approved.

| # | Control | What it does | Server work |
|---|---------|--------------|-------------|
| 1 | JD file replace / download | Upload a new JD file (text replaced after a confirmation), download the original | small |
| 2 | Duplicate project | New project with the same JD, requirements, scoring and factors, no CVs | small |
| 3 | Re-read requirements from JD | See T27 | none (T27) |
| 4 | Pause uploads | Stop accepting new CVs for this project without archiving it | small |
| 5 | Close date | Date after which uploads stop, with a reminder email before | medium |
| 6 | Auto-delete CVs after N days (per project) | Overrides the company retention for this project, never longer than the company's | medium |
| 7 | Default stage for new candidates | Choose New or Shortlisted when a score is above the threshold | medium |
| 8 | Auto-reject below a score | Moves candidates under a chosen score to Rejected (reversible, logged) | medium |
| 9 | Notify me | Email when scoring finishes or a new Grade A arrives, per project | medium |
| 10 | Who can see this project | Owner picks which team members may open it | large |
| 11 | Hide contact details by default | Default for new shared reports and downloads | small |
| 12 | Labels | Department, location, seniority tags to filter the project list | medium |
| 13 | Re-score everything | Re-run scoring after a settings change (cost estimate popup) | exists, expose |
| 14 | Export project | One download of requirements, scores and notes | medium |
| 15 | Change project owner | Hand the project to another team member | small |
| 16 | History | Who changed what and when (title, JD, weights, stage bulk moves) | medium |

Settings page is regrouped into sections (Details, Job description, Scoring, Candidates,
Notifications, Access, Danger zone), each a card, one Save per section, confirmations in popups.

---

## Common to every ticket

Approach described before building; tests for the happy path and every edge case above;
`/design` updated; secret scan, ruff, prettier, tsc and the touched tests before each push;
whole suite after T27. Copy stays minimal (headings and buttons); any wording comes from the
owner.
