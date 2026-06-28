# Spec: Profile Page Design

## 1. Overview

Replace the `GET /profile` stub (`"Profile page — coming in Step 4"`) with a real, designed page that confirms a successful login and gives the user a landing surface inside the app. This step is **purely the read-only profile shell** — name, email, and member-since date pulled from the `users` table, plus quiet placeholders for the expense features that arrive in Steps 5–9. No editing, no expense list, no statistics. It is **Step 4** of the Spendly roadmap and is the first authenticated page the user sees after signing in.

---

## 2. Depends on

- **Step 1 — Database setup** (complete). Uses the `users` table (`id`, `name`, `email`, `created_at`) via `database/db.py::get_db()`.
- **Step 2 — Registration** (complete). New accounts already populate the columns this page reads.
- **Step 3 — Login and logout** (complete). Relies on `session["user_id"]` + `session["user_name"]` being set on login, and on the nav swap that already renders `Profile` + `Sign out` when logged in.

---

## 3. Routes

- `GET /profile` — **replace the Step 4 stub** — renders `profile.html` with the logged-in user's row — **logged-in only** (redirects to `/login` if `session["user_id"]` is missing)

No other route changes. Edit/delete/expense routes stay as their Step 7–9 stubs.

---

## 4. Database changes

No database changes. The `users` table already has every column needed (`id`, `name`, `email`, `created_at`).

---

## 5. Templates

- **Create:**
  - `templates/profile.html` — extends `base.html`. Layout:
    - A centered profile card (`.profile-card`) with:
      - Avatar circle (`.profile-avatar`) showing the user's first initial in uppercase, on the `--accent` background
      - User's `name` as the page heading (DM Serif Display, h1)
      - User's `email` as a muted subline
      - A meta row showing **Member since &lt;Month Year&gt;** parsed from `users.created_at`
    - A "Coming soon" section below the card with three muted placeholder tiles for the upcoming steps — **Add expense** (Step 7), **Edit expense** (Step 8), **Delete expense** (Step 9). Each tile is a non-link, visually disabled (`.placeholder-tile`) — no `<a>` to the stub routes, since they still return raw strings.
    - A small "Signed in as &lt;email&gt;" line with a `Sign out` link via `url_for('logout')` (in addition to the nav `Sign out` — gives a clear in-page action).
- **Modify:** none. The nav already swaps to `Profile` + `Sign out` based on `session.user_id` from Step 3 — do not touch `base.html`.

---

## 6. Files to change

- `app.py`
  - Replace the `profile` view. It must:
    1. Check `session.get("user_id")`. If missing, `return redirect(url_for("login"))`.
    2. Call a new DB helper `get_user_by_id(user_id)` (see §7). If it returns `None` (stale session for a deleted user), call `session.clear()` and redirect to `url_for("login")`.
    3. Render `profile.html` passing `user=row` and a precomputed `member_since` string (e.g. `"June 2026"`).
  - Do **not** import `sqlite3` here for this work; the DB call lives in `database/db.py`.
- `database/db.py`
  - Add `get_user_by_id(user_id)` — parameterised `SELECT id, name, email, created_at FROM users WHERE id = ?`, returns the `sqlite3.Row` or `None`.
- `static/css/style.css`
  - Append a new `Profile page` section (with the existing comment-banner style) defining: `.profile-section`, `.profile-card`, `.profile-avatar`, `.profile-name`, `.profile-email`, `.profile-meta`, `.placeholder-grid`, `.placeholder-tile`, `.profile-signout`. Use **only** existing CSS variables — no new hex.

---

## 7. Files to create

- `templates/profile.html` — see §5
- `.claude/specs/04-profile-page-design.md` — this spec (already created by `/create-spec`)

---

## 8. New dependencies

No new dependencies. `datetime` from the stdlib is used in `app.py` to format `created_at` into `Month Year`.

---

## 9. Auth + redirect rules

- `GET /profile` while logged out → `302` to `url_for("login")`. Do **not** flash a message in this step (no `flash()` infrastructure yet) — a clean redirect is sufficient.
- `GET /profile` while logged in with a `user_id` that no longer exists in `users` → clear the session and redirect to `url_for("login")`. This guards against a seed-reset-during-dev edge case.
- Never trust `session["user_name"]` for the page body — re-fetch the row by `id` so a rename in the DB shows up immediately.

---

## 10. Date formatting

`users.created_at` is stored as a SQLite `datetime('now')` string (`"YYYY-MM-DD HH:MM:SS"`). In the route, parse with `datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")` and format as `dt.strftime("%B %Y")` → e.g. `"June 2026"`. Pass the result as `member_since` so the template stays formatting-free. If parsing fails for any reason, pass `member_since=None` and let the template hide the meta row with `{% if member_since %}`.

---

## 11. Rules for implementation

- Flask only — no extensions, no `flask-login`
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()`
- **Parameterised queries only** — never f-string into SQL
- All templates extend `base.html`
- Use **CSS variables** (`--ink`, `--accent`, `--accent-2`, `--paper-card`, `--border`, …) — never hardcode hex
- Use `url_for()` for every internal link — `login`, `logout`, `profile` itself, etc.
- Currency-related copy uses `₹` (the user uses INR throughout — no `$`)
- Route function stays thin: auth check → fetch row → format date → render. DB work lives in `database/db.py`.
- Do **not** implement the expense add/edit/delete tiles as links — they are visual placeholders only. Step 7 onwards will turn them into real CTAs.
- Do **not** add a profile-edit form, password change, or avatar upload. Those are out of scope for Step 4.
- Page-specific CSS goes in `style.css` under a new section header, **not** in `<style>` tags inside the template (per `CLAUDE.md`: "Page-specific styles → new `.css` file, not inline `<style>` tags" — append here, do not create a `profile.css` since the project has a single stylesheet).
- Reuse `.main-content` spacing; the profile page itself supplies its own padding via `.profile-section`.

---

## 12. Definition of done

- [ ] `GET /profile` while logged out redirects to `/login` with a `302`
- [ ] `GET /profile` while logged in renders `profile.html` (no raw string response)
- [ ] The page shows the user's `name` as the heading, their `email` as the subline, and `Member since <Month Year>` parsed from `created_at`
- [ ] The avatar circle shows the first character of `name` in uppercase, on `--accent` background with `--paper` text
- [ ] Three "Coming soon" placeholder tiles render for Add / Edit / Delete expense — none are clickable links
- [ ] An in-page `Sign out` link points to `url_for('logout')` and successfully logs the user out
- [ ] If `session["user_id"]` references a deleted user, the session is cleared and the user is redirected to `/login` (verified by manually deleting the row in `spendly.db` and refreshing)
- [ ] Nav still shows `Profile` + `Sign out` while on this page (no double-rendering, no nav regressions)
- [ ] No hardcoded URLs in `profile.html` — all internal links use `url_for()`
- [ ] No hardcoded hex colors in the new CSS — every color references a `--var`
- [ ] No `<style>` block inside `profile.html`
- [ ] `get_user_by_id` uses a parameterised query (`?` placeholder)
- [ ] No new pip packages; `requirements.txt` unchanged
- [ ] App still starts cleanly on port 5001 with `python app.py`
- [ ] Demo user (`demo@spendly.com` / `demo123`) signs in and lands on a profile page showing `Demo User`, `demo@spendly.com`, and the correct member-since month
