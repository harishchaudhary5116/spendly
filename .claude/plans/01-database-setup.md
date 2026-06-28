# Implementation Plan — 01 Database Setup

Source spec: `.claude/specs/01-database-setup.md`

## Goal

Replace the contract-only `database/db.py` with a working SQLite layer (`get_db`, `init_db`, `seed_db`), and wire startup initialization into `app.py`. No new routes, no new packages.

---

## Decisions resolved up-front

- **DB filename:** `expense_tracker.db` at repo root. CLAUDE.md pins this, and `.gitignore` already excludes it. Spec allowed either name; we pick the one already wired.
- **Categories list:** hard-coded module-level tuple in `db.py` so seed data and (future) forms read from one source. Spec lists 7 values; seed needs 8 expenses with at least one per category → one category gets two entries.
- **Seed dates:** spread across the current month (June 2026 per session date). Format `YYYY-MM-DD` only.
- **Connection lifecycle:** `init_db()` and `seed_db()` open their own short-lived connections and close them. Routes will get their own connections later (Step 3+). No Flask `g` caching yet — spec doesn't require it, and adding it now is scope creep.
- **Password hashing:** `werkzeug.security.generate_password_hash` (already in `requirements.txt`, default method).

---

## File-by-file changes

### 1. `database/db.py` — full implementation

Replace the comment-only file with:

**Imports**
- `sqlite3`
- `os` (to build absolute path to DB file beside the project root)
- `from werkzeug.security import generate_password_hash`

**Module-level constants**
- `DB_PATH` — absolute path to `expense_tracker.db` at repo root (compute via `os.path.dirname(os.path.dirname(__file__))`).
- `CATEGORIES` — tuple of the 7 fixed categories from spec §10: `("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other")`.

**`get_db()`**
1. `conn = sqlite3.connect(DB_PATH)`
2. `conn.row_factory = sqlite3.Row`
3. `conn.execute("PRAGMA foreign_keys = ON")` — must run on every connection (SQLite default is off).
4. Return `conn`.

**`init_db()`**
1. Open connection via `get_db()`.
2. Execute two `CREATE TABLE IF NOT EXISTS` statements matching spec §4:
   - `users(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))`
   - `expenses(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount REAL NOT NULL, category TEXT NOT NULL, date TEXT NOT NULL, description TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY(user_id) REFERENCES users(id))`
3. `conn.commit()`, `conn.close()`.

Note: SQLite `INTEGER PRIMARY KEY` is already rowid/autoincrementing — the explicit `AUTOINCREMENT` keyword matches the spec wording and prevents id reuse.

**`seed_db()`**
1. Open connection via `get_db()`.
2. Guard against duplicates: `SELECT COUNT(*) FROM users`. If `> 0`, close and return.
3. Insert demo user with parameterized `INSERT`:
   - `name="Demo User"`, `email="demo@spendly.com"`, `password_hash=generate_password_hash("demo123")`.
   - Capture `cursor.lastrowid` as `user_id`.
4. Insert 8 expenses in one `executemany` call. Distribution (one per category + one extra in Food):

   | # | category      | amount | date         | description           |
   |---|---------------|--------|--------------|-----------------------|
   | 1 | Food          | 250.00 | 2026-06-02   | Groceries             |
   | 2 | Food          | 180.50 | 2026-06-18   | Dinner with friends   |
   | 3 | Transport     | 90.00  | 2026-06-05   | Metro card top-up     |
   | 4 | Bills         | 1200.00| 2026-06-08   | Electricity bill      |
   | 5 | Health        | 450.00 | 2026-06-11   | Pharmacy              |
   | 6 | Entertainment | 350.00 | 2026-06-14   | Movie tickets         |
   | 7 | Shopping      | 1499.00| 2026-06-20   | New shoes             |
   | 8 | Other         | 200.00 | 2026-06-23   | Misc                  |

   All amounts in ₹ (INR). All dates within June 2026.
5. `conn.commit()`, `conn.close()`.

All SQL uses `?` placeholders — no f-strings, no `%` formatting.

---

### 2. `app.py` — wire startup init

Two edits only:

**a. Add import** (top of file, after Flask import):
```python
from database.db import init_db, seed_db
```
`get_db` is not imported here — it's only needed by routes that will be added in later steps. Importing what we don't use is noise.

**b. Run init/seed once at startup**, immediately after `app = Flask(__name__)`:
```python
with app.app_context():
    init_db()
    seed_db()
```

Both helpers are idempotent, so this is safe on every reload under `debug=True`.

Do **not** touch the existing routes or the `if __name__ == "__main__"` block.

---

## Out of scope (do not touch)

- All placeholder stub routes (`/logout`, `/profile`, `/expenses/*`) — they stay as plain-string returns per spec §3 and CLAUDE.md route table.
- Templates, CSS, JS.
- `requirements.txt` — no new packages (spec §9).
- Tests — spec defines no test files for Step 1. Manual verification only.

---

## Verification steps

After implementation, run from the repo root:

1. **Startup smoke test** — `python app.py` should print Flask's normal dev banner with no traceback. Confirms `init_db()` + `seed_db()` ran cleanly inside `app_context`.
2. **DB file exists** — `ls expense_tracker.db` should show a non-zero file at repo root.
3. **Schema check** —
   ```
   sqlite3 expense_tracker.db ".schema"
   ```
   Both `users` and `expenses` tables present with the columns from spec §4.
4. **Seed check** —
   ```
   sqlite3 expense_tracker.db "SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM expenses;"
   ```
   Expect `1` and `8`.
5. **Idempotency** — stop and restart `python app.py`. Re-run query 4. Counts must still be `1` and `8` (no duplicates).
6. **FK enforcement** —
   ```
   sqlite3 expense_tracker.db
   PRAGMA foreign_keys = ON;
   INSERT INTO expenses(user_id, amount, category, date) VALUES (999, 10, 'Food', '2026-06-01');
   ```
   Must fail with a foreign key constraint error.
7. **UNIQUE email** —
   ```
   sqlite3 expense_tracker.db "INSERT INTO users(name, email, password_hash) VALUES ('x', 'demo@spendly.com', 'y');"
   ```
   Must fail with a UNIQUE constraint error.

---

## Definition of done (mirrors spec §14)

- [ ] `expense_tracker.db` created on first `python app.py` run
- [ ] `users` and `expenses` tables have correct columns and constraints
- [ ] Demo user `demo@spendly.com` exists with hashed password (not plaintext)
- [ ] 8 seed expenses present, covering all 7 categories
- [ ] Restarting the app does not duplicate seed rows
- [ ] App starts with no errors or warnings beyond Flask's normal dev output
- [ ] FK constraint and UNIQUE email constraint both enforced
- [ ] Every SQL statement in `db.py` uses `?` parameter placeholders
