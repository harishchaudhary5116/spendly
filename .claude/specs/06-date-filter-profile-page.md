# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the `/profile` page so users can scope their
dashboard (summary stats, category breakdown, and recent transactions) to a
specific window of time. The filter is driven by two GET query parameters
(`start_date` and `end_date`) plus a small set of preset shortcuts ("This
month", "Last 30 days", "All time"). The user-info card is unaffected — the
filter only changes the three data sections that read from the `expenses`
table. When no filter is supplied, the page behaves exactly as it does today
(all expenses, newest first).

## Depends on
- Step 1: Database setup (`expenses.date` exists as `TEXT` in `YYYY-MM-DD` format)
- Step 2: Registration
- Step 3: Login / Logout (`session["user_id"]` set on login)
- Step 4: Profile page static UI
- Step 5: Backend routes for profile page (`database/queries.py` exists with
  `get_summary_stats`, `get_recent_transactions`, `get_category_breakdown`)

## Routes
No new routes. The existing `GET /profile` route is modified to read
`start_date` and `end_date` from `request.args` and pass them through to the
query helpers.

## Database changes
No database changes. `expenses.date` is already stored as `TEXT` in
`YYYY-MM-DD` format, which sorts and compares correctly as a string.

## Templates
- **Modify:** `templates/profile.html`
  - Add a `<form method="get" action="{{ url_for('profile') }}">` above the
    summary card containing two `<input type="date">` fields (`start_date`,
    `end_date`), a "Apply" submit button, and a "Clear" link back to
    `url_for('profile')`.
  - Above the form, render three preset links: "This month", "Last 30 days",
    "All time" — each is an `<a href>` to `/profile?start_date=…&end_date=…`.
  - Highlight the active preset based on the current query string.
  - When a filter is active, render a small caption above the summary card
    (e.g. "Showing 1 Jun 2026 → 29 Jun 2026") so the user knows what they're
    looking at.
  - If the filtered range has no expenses, the existing empty-state copy
    ("No transactions yet.", "No spending categorised yet.") must still render
    — do not hide the sections.

## Files to change
- `app.py` — `profile()` view reads `start_date` / `end_date` from
  `request.args`, validates them, and forwards them to the three query
  helpers. Also computes the preset URLs and active-preset flag.
- `database/queries.py` — `get_summary_stats`, `get_recent_transactions`, and
  `get_category_breakdown` each gain optional `start_date=None` and
  `end_date=None` parameters and append `AND date >= ?` / `AND date <= ?`
  clauses when supplied.
- `templates/profile.html` — add the filter form, preset links, and active
  range caption as described above.
- `static/css/style.css` — add styles for `.date-filter`, `.date-filter-form`,
  `.date-filter-presets`, `.date-filter-preset`, `.date-filter-preset.is-active`,
  and `.date-filter-caption`. Reuse existing CSS variables (`--ink`, `--paper`,
  `--accent`, `--border`) — no hardcoded colours.

## Files to create
No new files. The feature reuses existing modules.

## New dependencies
No new dependencies. Use `datetime.date` from the stdlib for date parsing and
preset computation.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-string user input into SQL
- Passwords hashed with werkzeug (unchanged from prior steps)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags in `profile.html`
- Currency must always display as ₹
- Date parsing must use `datetime.strptime(value, "%Y-%m-%d").date()`; any
  `ValueError` means the parameter is invalid and the filter is treated as
  absent (the page renders unfiltered rather than 400-ing)
- If both dates are supplied and `start_date > end_date`, treat the filter as
  absent and render unfiltered — no exception
- Query helpers must keep their existing signatures backwards-compatible:
  `start_date` and `end_date` are keyword-only optional parameters with
  default `None`
- The filter applies to `expenses.date` only — `users.created_at` is never
  filtered (the user info card always shows the same data)
- The "This month" preset uses the current calendar month (1st of month to
  today). "Last 30 days" uses today minus 29 days to today (inclusive — 30
  days total). "All time" clears both parameters.
- Preset URLs must be built with `url_for('profile', start_date=…, end_date=…)`
  — never hardcoded query strings
- Date `<input type="date">` fields must echo back the currently active
  `start_date` / `end_date` via the `value=` attribute so the form does not
  reset on submit

## Definition of done
- [ ] Visiting `/profile` with no query params still renders the full dashboard
      with all 8 seed expenses (₹4219.50 total, top category "Shopping")
- [ ] Visiting `/profile?start_date=2026-06-01&end_date=2026-06-10` shows only
      the seed expenses dated within that window (3 rows totalling ₹1540.00,
      top category "Bills") with summary stats, category breakdown, and the
      transactions list all recomputed accordingly
- [ ] The summary "Total spent" updates to match the filtered range
- [ ] The "Transactions" count updates to match the filtered range
- [ ] The "Top category" reflects only the filtered expenses
- [ ] The category breakdown percentages still sum to 100 within the filtered
      range
- [ ] The active preset link is visually highlighted when its URL matches the
      current query string
- [ ] Clicking "All time" returns to the unfiltered `/profile`
- [ ] Submitting the form with an invalid date (e.g. `start_date=banana`) or
      with `start_date` later than `end_date` renders the unfiltered page
      without raising a 500
- [ ] Submitting the form with a range that contains no expenses renders the
      empty-state copy in each section ("No transactions yet.", "No spending
      categorised yet.") and a Total spent of ₹0.00
- [ ] The user-info card (name, email, member since) is identical regardless
      of filter
