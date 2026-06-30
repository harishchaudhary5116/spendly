# Spec: Add Expense

## Overview
Step 7 turns the `/expenses/add` placeholder route into a working
form that lets the signed-in user record a new expense. The page
renders a single form (amount, category, date, description) on `GET`
and inserts a row into the `expenses` table on `POST`, then
redirects to `/profile` where the new entry appears in the summary
stats, category breakdown, and recent transactions list. This is the
first write path into the `expenses` table from the UI — every other
expense feature (edit, delete, analytics) depends on it.

## Depends on
- Step 1: Database setup (`expenses` table exists with the columns
  `user_id`, `amount`, `category`, `date`, `description`)
- Step 2: Registration
- Step 3: Login / Logout (`session["user_id"]` set on login)
- Step 4: Profile page static UI
- Step 5: Backend routes for profile page (so the new row shows up
  in stats/breakdown/transactions after redirect)
- Step 6: Date filter on profile page (no interaction required, but
  the new row must respect the filter)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in
- `POST /expenses/add` — validate and insert a new expense, then
  redirect to `/profile` — logged-in

Both forms of the route redirect to `/login` if no `user_id` is in
the session. The existing stub returning `"Add expense — coming in
Step 7"` is removed.

## Database changes
No database changes. The `expenses` table already has every column
this feature needs (`user_id`, `amount`, `category`, `date`,
`description`). The category list comes from the existing
`CATEGORIES` tuple in `database/db.py`.

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - Single `<form method="post" action="{{ url_for('add_expense') }}">`
    with four fields:
    - `amount` — `<input type="number" step="0.01" min="0.01" max="9999999.99" required>`
    - `category` — `<select required>` populated from `categories`
      passed in by the view (defaults to "Food" if no prior value)
    - `date` — `<input type="date" required>` defaulting to today
      (`YYYY-MM-DD`) on GET
    - `description` — `<input type="text" maxlength="200">` (optional)
  - Submit button labelled "Add expense" and a "Cancel" link back to
    `url_for('profile')`
  - Echoes back the prior `amount`, `category`, `date`,
    `description` values via `value=` / `selected` when re-rendering
    after a validation error
  - Renders a single `error` message above the form when present
  - Header above the form: `<h1>Add expense</h1>`

## Files to change
- `app.py`
  - Replace the existing stub:
    ```python
    @app.route("/expenses/add")
    def add_expense():
        return "Add expense — coming in Step 7"
    ```
  - With a `GET`/`POST` route that requires a logged-in session,
    validates form input, calls a new `create_expense(...)` helper,
    and redirects to `url_for('profile')` on success.
  - Import `create_expense` and `CATEGORIES` from
    `database.db` (or `database.queries` — see below).
- `database/db.py`
  - Add `create_expense(user_id, amount, category, date, description)`
    that opens a connection via `get_db()`, runs a parameterised
    `INSERT INTO expenses (...) VALUES (?, ?, ?, ?, ?)`, commits, and
    closes the connection. Returns the new row id.
- `static/css/style.css`
  - Add styles for `.add-expense-section`, `.add-expense-card`,
    `.add-expense-form`, `.form-error`, and reuse existing
    `.form-group`, `.form-input`, `.btn-primary`, `.btn-ghost`
    tokens. No new colour hex values — use existing CSS variables.
- `templates/base.html`
  - Add a "Add expense" link to the nav when `session.user_id` is
    set, pointing to `url_for('add_expense')`. Keep the existing
    nav items as-is.

## Files to create
- `templates/add_expense.html` — described above
- `.claude/specs/07-add-expense.md` — this spec

## New dependencies
No new dependencies. Use `datetime.date.today().isoformat()` from the
stdlib for the default date.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-string user input into SQL
- Passwords hashed with werkzeug (unchanged from prior steps)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags in `add_expense.html`
- Currency must always display as ₹
- The `category` value submitted by the form **must** be validated
  against `CATEGORIES` — anything else is rejected as invalid, never
  inserted (defends against tampered `<select>` values)
- `amount` must parse as a positive float strictly greater than `0`
  and ≤ `9_999_999.99`; reject blanks, negatives, zero, and any
  non-numeric value
- `date` must parse via `datetime.strptime(value, "%Y-%m-%d").date()`
  and must not be in the future (`> date.today()` is rejected)
- `description` is optional; when present it is trimmed and capped at
  200 characters. An empty / whitespace-only description is stored
  as `NULL` (not as an empty string)
- The view must read `session["user_id"]` and pass it to
  `create_expense` — never trust a `user_id` value from the form
- On validation failure, re-render `add_expense.html` with the
  original field values pre-filled and a single `error` message;
  return HTTP 200 (not a redirect — the user sees the error inline)
- On success, redirect with `302` to `url_for('profile')` (PRG
  pattern — never render the form's response directly)
- The route must accept both `GET` and `POST`; any other method
  returns Flask's default 405
- Logged-out users hitting either method get a redirect to
  `url_for('login')` — they never see the form and the POST never
  inserts
- The form must use `url_for('add_expense')` as its `action` — never
  hardcode `/expenses/add`
- Do not change the `/profile` view, query helpers, or filter logic
  in this step — scope edits tightly to add-expense only

## Definition of done
- [ ] `GET /expenses/add` while logged in renders the form with the
      date input pre-filled to today (`YYYY-MM-DD`), the category
      `<select>` populated with all 7 categories from `CATEGORIES`,
      and no error message
- [ ] `GET /expenses/add` while logged out redirects to `/login`
- [ ] `POST /expenses/add` with valid values
      (`amount=125.50`, `category=Food`, `date=2026-06-30`,
      `description=Lunch`) inserts one row and redirects (302) to
      `/profile`
- [ ] After the redirect, `/profile` shows the new transaction in
      "Recent transactions", the new total in "Total spent", and the
      transaction count incremented by 1
- [ ] `POST /expenses/add` while logged out does **not** insert a
      row and redirects to `/login`
- [ ] `POST` with `amount=0`, `amount=-5`, `amount=abc`, or a blank
      amount re-renders the form with an inline error and inserts
      nothing
- [ ] `POST` with `category=NotACategory` re-renders the form with
      an inline error and inserts nothing
- [ ] `POST` with `date=2099-01-01` (future) re-renders the form
      with an inline error and inserts nothing
- [ ] `POST` with `date=banana` re-renders the form with an inline
      error and inserts nothing (no 500)
- [ ] `POST` with an empty / whitespace-only `description` stores
      `NULL` in the `description` column, not `""`
- [ ] `POST` with `description` longer than 200 characters is
      truncated or rejected (pick one; spec requires `maxlength=200`
      on the input plus a server-side cap)
- [ ] The form re-render after a validation error preserves the
      user's typed `amount`, `category`, `date`, and `description`
- [ ] The new "Add expense" nav link only appears when
      `session.user_id` is set
- [ ] The currency symbol shown on the form (e.g. amount prefix) is
      ₹, not $
- [ ] No raw SQL string contains an f-string of user input — only
      `?` placeholders
