# Spec: Edit Expense

## Overview
Step 8 turns the `/expenses/<id>/edit` placeholder route into a working
form that lets the signed-in user modify one of their own expenses. The
page renders a form pre-filled with the expense's current `amount`,
`category`, `date`, and `description` on `GET`, and on `POST` runs the
same validation as add-expense, updates the row, and redirects to
`/profile`. The route must enforce ownership — a user may only ever
edit expenses that belong to them; every other case (missing row,
someone else's row) returns `404`. This is the first write-through-id
path in the app and is the direct dependency for Step 9 (delete).

## Depends on
- Step 1: Database setup (`expenses` table with `id`, `user_id`,
  `amount`, `category`, `date`, `description`)
- Step 3: Login / Logout (`session["user_id"]` set on login)
- Step 5: Backend routes for profile page (`get_recent_transactions`
  provides the list the edit link is rendered from)
- Step 7: Add expense — this feature reuses `CATEGORIES`, the CSRF
  helpers `_get_csrf_token` / `_csrf_valid`, the `_parse_date` helper,
  and the same amount/category/date/description validation rules

## Routes
- `GET /expenses/<int:id>/edit` — render the edit-expense form
  pre-filled with the row's current values — logged-in, owner only
- `POST /expenses/<int:id>/edit` — validate and update the expense,
  then redirect to `/profile` — logged-in, owner only

Both methods redirect to `/login` if no `user_id` is in the session,
and both `abort(404)` if the expense id does not exist **or** does not
belong to `session["user_id"]`. The existing stub returning
`"Edit expense — coming in Step 8"` is removed.

## Database changes
No database changes. The `expenses` table already has every column
this feature needs. No new indexes required — `id` is the primary key.

## Templates
- **Create:** `templates/edit_expense.html`
  - Extends `base.html`
  - Single `<form method="post"
    action="{{ url_for('edit_expense', id=expense.id) }}">` with the
    same four fields as add-expense:
    - `amount` — `<input type="number" step="0.01" min="0.01"
      max="9999999.99" required>` pre-filled with the row's amount
    - `category` — `<select required>` populated from `categories`
      with the row's current category `selected`
    - `date` — `<input type="date" required>` pre-filled with the
      row's date (`YYYY-MM-DD`)
    - `description` — `<input type="text" maxlength="200">` (optional)
      pre-filled with the row's description
  - Hidden CSRF field: `<input type="hidden" name="csrf_token"
    value="{{ csrf_token }}">`
  - Submit button labelled "Save changes" and a "Cancel" link back to
    `url_for('profile')`
  - Echoes back the submitted `amount`, `category`, `date`,
    `description` values via `value=` / `selected` when re-rendering
    after a validation error (not the DB values)
  - Renders a single `error` message above the form when present
  - Header above the form: `<h1>Edit expense</h1>` with subtitle
    `Update this transaction in ₹`

- **Modify:** `templates/profile.html`
  - Add an "Edit" link next to each transaction row in the "Recent
    transactions" list, pointing at
    `{{ url_for('edit_expense', id=tx.id) }}`
  - Keep the row layout consistent — the action column reuses the
    same grid structure (add a new grid column for actions or a
    trailing `.tx-actions` cell — pick one and mirror it in the
    `.transactions-header` row)
  - Only render the link when `session.user_id` is set (defence in
    depth — the profile page already requires auth, but the template
    should not assume that)

## Files to change
- `app.py`
  - Replace the existing stub:
    ```python
    @app.route("/expenses/<int:id>/edit")
    def edit_expense(id):
        return "Edit expense — coming in Step 8"
    ```
  - With a `GET`/`POST` route that:
    - requires a logged-in session (redirect to `login` otherwise)
    - loads the expense via a new `get_expense_by_id(id, user_id)`
      helper; `abort(404)` if `None`
    - on `GET` renders `edit_expense.html` pre-filled with the row
    - on `POST` re-checks CSRF, runs the same validation as
      add-expense, and calls a new
      `update_expense(id, user_id, amount, category, date, description)`
      helper
    - redirects to `url_for('profile')` on success
  - Add `update_expense` to the import from `database.db` and add
    `get_expense_by_id` to the import from `database.queries`.
- `database/db.py`
  - Add `update_expense(expense_id, user_id, amount, category, date,
    description)` that opens a connection via `get_db()`, runs a
    parameterised
    `UPDATE expenses SET amount = ?, category = ?, date = ?,
    description = ? WHERE id = ? AND user_id = ?`, commits, and closes
    the connection. Returns the number of rows updated (`cursor.rowcount`).
- `database/queries.py`
  - Add `get_expense_by_id(expense_id, user_id)` that opens a
    connection via `get_db()`, runs a parameterised
    `SELECT id, amount, category, date, description FROM expenses
    WHERE id = ? AND user_id = ?`, closes the connection, and returns
    a plain dict (`{"id", "amount", "category", "date",
    "description"}`) or `None`.
  - Update `get_recent_transactions` to also select `id` and include
    it in each returned dict so the profile template can build the
    edit URL. Do not change ordering, limits, or the filter clause.
- `static/css/style.css`
  - Add styles for `.edit-expense-section`, `.edit-expense-container`,
    `.edit-expense-header`, `.edit-expense-title`,
    `.edit-expense-subtitle`, `.edit-expense-card`,
    `.edit-expense-form`, `.edit-expense-amount-wrap`,
    `.edit-expense-amount-prefix`, `.edit-expense-amount-input`,
    `.edit-expense-actions`. It is fine (encouraged) to reuse the
    add-expense selectors by targeting both — e.g.
    `.add-expense-card, .edit-expense-card { ... }` — so the two
    forms stay visually identical.
  - Add a `.tx-edit-link` (or similar) selector for the per-row edit
    link on the profile transactions list. No hardcoded hex — reuse
    `--accent`, `--accent-2`, `--border`, `--ink`, etc.

## Files to create
- `templates/edit_expense.html` — described above
- `.claude/specs/08-edit-expense.md` — this spec

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-string user input into SQL
- Passwords hashed with werkzeug (unchanged from prior steps)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags in `edit_expense.html`
- Currency must always display as ₹
- **Ownership check is non-negotiable**: every `SELECT` and `UPDATE`
  in this feature must include `WHERE ... AND user_id = ?`. The route
  never trusts the URL `id` alone. A logged-in user attempting to
  edit another user's expense gets a `404`, never a `403` message
  that would leak existence, and never a successful update.
- CSRF: `POST /expenses/<id>/edit` must validate `csrf_token` against
  `session["csrf_token"]` using the existing `_csrf_valid` helper.
  Invalid CSRF redirects to the same edit page (`GET`) — never
  updates the row.
- The `category` value submitted by the form **must** be validated
  against `CATEGORIES` — anything else is rejected as invalid, never
  written (defends against tampered `<select>` values)
- `amount` must parse as a positive float strictly greater than `0`
  and ≤ `9_999_999.99`; reject blanks, negatives, zero, and any
  non-numeric value. Use `math.isfinite` to reject `NaN`/`inf`.
- `date` must parse via `_parse_date(value)` and must not be in the
  future (`> date.today()` is rejected)
- `description` is optional; when present it is trimmed and capped at
  200 characters. An empty / whitespace-only description is stored
  as `NULL` (not as `""`)
- On validation failure, re-render `edit_expense.html` with the
  submitted field values pre-filled (not the DB values) and a single
  `error` message; return HTTP 200
- On success, redirect with `302` to `url_for('profile')` (PRG
  pattern — never render the form's response directly)
- The route must accept both `GET` and `POST`; any other method
  returns Flask's default 405
- Logged-out users hitting either method get a redirect to
  `url_for('login')` — they never see the form and the POST never
  updates
- The form must use `url_for('edit_expense', id=expense.id)` as its
  `action` — never hardcode `/expenses/<id>/edit`
- Do not change the `/profile` view logic, filter behaviour, or
  `create_expense` in this step — scope edits to edit-expense only
  (plus the small `get_recent_transactions` addition of `id`)
- Do not implement delete in this step — the delete route stays a
  stub until Step 9

## Definition of done
- [ ] `GET /expenses/<id>/edit` while logged in as the owner renders
      the form pre-filled with the row's current `amount`, `category`
      (selected in the `<select>`), `date` (in `YYYY-MM-DD`), and
      `description`, and shows no error message
- [ ] `GET /expenses/<id>/edit` while logged out redirects to `/login`
- [ ] `GET /expenses/<id>/edit` for an `id` that does not exist
      returns a `404`
- [ ] `GET /expenses/<id>/edit` for an `id` owned by a **different**
      user returns a `404` (not `403`, not a redirect, not the form)
- [ ] `POST /expenses/<id>/edit` with valid values as the owner
      updates the row and redirects (302) to `/profile`
- [ ] After the redirect, `/profile` reflects the updated `amount` in
      "Total spent" and "By category", and the updated fields in the
      "Recent transactions" row
- [ ] `POST /expenses/<id>/edit` while logged out does **not** update
      the row and redirects to `/login`
- [ ] `POST /expenses/<id>/edit` for someone else's expense returns
      `404` and does **not** update the row
- [ ] `POST` with `amount=0`, `amount=-5`, `amount=abc`, or a blank
      amount re-renders the form with an inline error and does not
      update the row
- [ ] `POST` with `category=NotACategory` re-renders the form with an
      inline error and does not update the row
- [ ] `POST` with `date=2099-01-01` (future) re-renders the form with
      an inline error and does not update the row
- [ ] `POST` with `date=banana` re-renders the form with an inline
      error and does not update the row (no `500`)
- [ ] `POST` with an empty / whitespace-only `description` writes
      `NULL` to the `description` column, not `""`
- [ ] `POST` with a missing / mismatched `csrf_token` does not update
      the row (redirects back to the edit form)
- [ ] The form re-render after a validation error preserves the
      user's typed `amount`, `category`, `date`, and `description`
      (not the DB values)
- [ ] The profile page's "Recent transactions" list renders an
      "Edit" link per row that points at
      `/expenses/<id>/edit` for that specific expense
- [ ] The currency symbol shown on the form (e.g. amount prefix) is
      ₹, not $
- [ ] No raw SQL string contains an f-string of user input — only
      `?` placeholders
- [ ] `python app.py` starts on port 5001 with no import errors, and
      `pytest` still passes (existing add-expense tests unaffected)
