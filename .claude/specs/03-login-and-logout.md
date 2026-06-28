# Spec: Login and Logout

## 1. Overview

Turn the existing `GET /login` page into a working sign-in flow and convert the `/logout` stub into a real session-clearing route. A returning user submits the login form, the server looks up the row by email, verifies the password against the stored `pbkdf2:sha256` hash, and on success stores the user's id in the Flask `session` before redirecting to the (still-stub) profile page. Visiting `/logout` clears the session and returns the user to the landing page. This is **Step 3** of the Spendly roadmap and unlocks every later authenticated feature (profile editing, expense CRUD).

---

## 2. Depends on

- **Step 1 — Database setup** (complete). Relies on the `users` table and `database/db.py::get_db()`.
- **Step 2 — Registration** (complete). Relies on `create_user()` producing `pbkdf2:sha256` hashes that `werkzeug.security.check_password_hash` can verify, and on the `/login?registered=1` success banner already wired into `templates/login.html`.

---

## 3. Routes

- `GET /login` — already implemented, renders `login.html` — **public** (extended to also pass through a prefilled `email` on validation error)
- `POST /login` — **new** — validates credentials, sets `session["user_id"]` + `session["user_name"]`, redirects to `/profile` on success or re-renders `login.html` with an error — **public**
- `GET /logout` — **replace the Step 3 stub** — clears the session and redirects to `/` — **logged-in only** (if no session, still safe to call; just redirect)

The existing `login` view function in `app.py` will be extended to accept both `GET` and `POST` (no second function). The existing `logout` stub will be replaced in place.

---

## 4. Database changes

No database changes. The `users` table already has every column needed (`id`, `name`, `email`, `password_hash`).

---

## 5. Templates

- **Create:** none
- **Modify:**
  - `templates/login.html`
    - Change `action="/login"` → `action="{{ url_for('login') }}"` (per project rule: no hardcoded URLs)
    - Add `value="{{ email or '' }}"` to the email input so the form repopulates on validation error (do **not** repopulate password)
  - `templates/base.html`
    - Swap the nav links based on session: when `session.user_id` is set, show `Profile` + `Sign out`; otherwise show the existing `Sign in` + `Get started`. Use `url_for('profile')` and `url_for('logout')`. Reuse the existing `.nav-cta` class for the primary action.

---

## 6. Files to change

- `app.py`
  - Import `session` from `flask` (and `check_password_hash` indirectly via the new DB helper)
  - Set `app.secret_key` from the `SPENDLY_SECRET_KEY` environment variable, falling back to a clearly-marked dev-only default string. Add a one-line comment noting it must be overridden in production.
  - Extend the `login` view to handle `POST`: validate presence, call `authenticate_user()`, set `session["user_id"]` + `session["user_name"]` on success and redirect to `url_for("profile")`, otherwise re-render `login.html` with `error="Invalid email or password."` and the entered `email`.
  - Replace the `logout` stub: call `session.clear()` then `redirect(url_for("landing"))`.
- `database/db.py`
  - Add `authenticate_user(email, password)` — looks up the row by email with a parameterised query, returns the row (`sqlite3.Row`) if `check_password_hash(row["password_hash"], password)` succeeds, otherwise returns `None`. Never raises on bad credentials — caller treats `None` as the failure case.
- `templates/login.html` — see §5
- `templates/base.html` — see §5

---

## 7. Files to create

- None

---

## 8. New dependencies

No new dependencies. `flask.session` and `werkzeug.security.check_password_hash` are already available.

---

## 9. Validation rules

The POST handler must validate, in this order, and re-render `login.html` with `error` on the first failure:

1. `email` and `password` both present and non-empty after `.strip()` on email (do **not** strip password)
2. `authenticate_user(email, password)` returns a row

For both failure modes use the **same** generic message — `"Invalid email or password."` — so the form does not reveal whether the email exists. The entered `email` value must be passed back to the template so the user does not retype it. The `password` value must never be passed back.

---

## 10. Session contract

- `session["user_id"]` — int, the `users.id` of the authenticated user
- `session["user_name"]` — str, the `users.name` (used by the nav greeting in later steps)
- No other keys are set by this step. Step 4 (Profile) will read these.
- `session.clear()` is the only way to log out; do not pop individual keys.

---

## 11. Rules for implementation

- Flask only — no `flask-login`, no other extensions
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`
- **Parameterised queries only** — never f-string into SQL
- Password verification with `werkzeug.security.check_password_hash` — never compare hashes manually, never compare raw passwords
- Never store the raw password, never log it, never pass it back to the template
- All templates extend `base.html`
- Use **CSS variables** (`--ink`, `--accent`, `--border`, …) — never hardcode hex
- Use `url_for()` for every internal link — including the new nav links
- Route function stays thin: validate → call `authenticate_user()` → set session and redirect, or re-render. DB work lives in `database/db.py`.
- Use `abort()` for HTTP errors; bad credentials are user-facing and re-render the form (not `abort`)
- `app.secret_key` must be set **before** the first request — set it at module level near the `app = Flask(__name__)` line, not inside a route
- Do **not** create a `/dashboard` or `/profile` template in this step — `/profile` remains the Step 4 stub; we only redirect to it

---

## 12. Definition of done

- [ ] `GET /login` still renders the form unchanged (plus the success banner from Step 2 still works via `?registered=1`)
- [ ] Submitting valid credentials redirects to `/profile` and `session["user_id"]` + `session["user_name"]` are populated
- [ ] Submitting a wrong password **or** an unknown email re-renders the form with `"Invalid email or password."` and the entered email pre-filled
- [ ] Submitting an empty email or empty password re-renders the form with `"Invalid email or password."` (same generic message — no enumeration)
- [ ] Password is never echoed back into the form
- [ ] `GET /logout` clears the session and redirects to `/`; visiting `/logout` while already logged out is a harmless redirect to `/`
- [ ] The nav bar shows `Profile` + `Sign out` when logged in, and `Sign in` + `Get started` when logged out — verified by logging in, refreshing any page, then logging out and refreshing again
- [ ] No template hardcodes `/login`, `/logout`, or `/profile` — all use `url_for()`
- [ ] `app.secret_key` is set from `SPENDLY_SECRET_KEY` env var with a documented dev fallback
- [ ] Demo user (`demo@spendly.com` / `demo123`) from Step 1's seed can sign in successfully
- [ ] No new pip packages; `requirements.txt` unchanged
- [ ] App still starts cleanly on port 5001 with `python app.py`
