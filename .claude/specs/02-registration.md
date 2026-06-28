# Spec: Registration

## 1. Overview

Turn the existing `GET /register` page into a working sign-up flow. A new visitor submits the registration form, the server validates the input, hashes the password with `werkzeug`, inserts a row into the `users` table, and redirects them to the login page. This is **Step 2** of the Spendly roadmap and unlocks all later authenticated features (login, profile, expense CRUD).

---

## 2. Depends on

- **Step 1 — Database setup** (complete). Relies on `users` table with `UNIQUE` email and `database/db.py::get_db()` for connections.

---

## 3. Routes

- `GET /register` — already implemented, renders `register.html` — **public**
- `POST /register` — **new** — validates form, creates user, redirects to `/login?registered=1` on success or re-renders `register.html` with an error — **public**

The existing `register` view function in `app.py` will be extended to accept both `GET` and `POST` (no second function).

---

## 4. Database changes

No database changes. The `users` table already has `name`, `email` (UNIQUE), `password_hash`, and `created_at`.

---

## 5. Templates

- **Create:** none
- **Modify:**
  - `templates/register.html`
    - Change `action="/register"` → `action="{{ url_for('register') }}"` (per project rule: no hardcoded URLs)
    - Add `value="{{ name or '' }}"` to the name input and `value="{{ email or '' }}"` to the email input so the form repopulates on validation error (do **not** repopulate password)
  - `templates/login.html`
    - Show a success banner when redirected with `?registered=1` (small, uses existing `.auth-error`-style class but a `.auth-success` variant — add to `style.css`)

---

## 6. Files to change

- `app.py` — extend the `register` view to handle `POST`; import `request`, `redirect`, `url_for`, `flash` is **not** used (keep it simple — pass error directly to template)
- `database/db.py` — add a single helper `create_user(name, email, password)` that hashes the password and inserts the row; raises `sqlite3.IntegrityError` on duplicate email so the route can catch it
- `templates/register.html` — see §5
- `templates/login.html` — see §5
- `static/css/style.css` — add `.auth-success` style (reuse existing tokens: `--accent`, `--border`, etc.)

---

## 7. Files to create

- None

---

## 8. New dependencies

No new dependencies. `werkzeug.security.generate_password_hash` is already in use in `database/db.py`.

---

## 9. Validation rules

The POST handler must validate, in this order, and re-render `register.html` with `error` on the first failure:

1. `name`, `email`, `password` all present and non-empty after `.strip()`
2. `name` length between 2 and 80 characters
3. `email` matches a simple regex (`^[^@\s]+@[^@\s]+\.[^@\s]+$`) and is ≤ 120 characters
4. `password` length ≥ 8
5. Email is not already taken — handled by catching `sqlite3.IntegrityError` from `create_user()`

Error messages are short, human, sentence-case (e.g. `"That email is already registered."`). The same `name` and `email` values must be passed back to the template so the user does not retype them.

---

## 10. Rules for implementation

- Flask only — no extensions
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`
- **Parameterised queries only** — never f-string into SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` using `method="pbkdf2:sha256"` (match Step 1 style)
- Never store the raw password, never log it, never pass it back to the template
- All templates extend `base.html`
- Use **CSS variables** (`--ink`, `--accent`, `--border`, …) — never hardcode hex
- Use `url_for()` for every internal link
- Route function stays thin: validate → call `create_user()` → redirect or re-render. DB work lives in `database/db.py`
- Use `abort()` for HTTP errors; validation errors are user-facing and re-render the form (not `abort`)
- No session login on successful registration — Step 3 handles login

---

## 11. Definition of done

- [ ] `GET /register` still renders the form unchanged
- [ ] Submitting a valid new registration inserts a row in `users` and redirects to `/login?registered=1`
- [ ] The login page shows a success banner when `?registered=1` is present
- [ ] Stored `password_hash` is a `pbkdf2:sha256` hash (not the raw password) — verify by opening `spendly.db`
- [ ] Submitting an already-registered email re-renders the form with `"That email is already registered."` and the previously entered name + email pre-filled
- [ ] Submitting an empty field, a too-short name, a malformed email, or a password shorter than 8 chars re-renders the form with a specific error
- [ ] Password is never echoed back into the form
- [ ] No template hardcodes `/register` or `/login` — both use `url_for()`
- [ ] No new pip packages; `requirements.txt` unchanged
- [ ] App still starts cleanly on port 5001 with `python app.py`
