# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Spendly — a Flask-based personal expense tracker. The project is structured as an incremental learning exercise: many routes in `app.py` are placeholder stubs ("coming in Step N") and `database/db.py` is a contract-only file describing functions (`get_db`, `init_db`, `seed_db`) that need to be implemented. When asked to add functionality, check whether it corresponds to one of these placeholder steps before designing something new.

## Commands

```bash
# First-time setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run dev server — http://127.0.0.1:5001
python app.py

# Tests
pytest                            # all tests
pytest tests/test_foo.py          # single file
pytest -k "test_name"             # single test by name
pytest -s                         # show stdout
```

The server is hard-coded to port **5001** with `debug=True`. The expected SQLite file is `spendly.db` at the repo root (gitignored).

## Architecture

- **`app.py`** — single-file Flask app. All routes live here; there is no blueprint structure. Routes are split into "implemented" (landing, register, login, terms, privacy) and "placeholder" stubs that return plain strings.
- **`database/db.py`** — intended home for SQLite helpers. Currently empty (contract comments only). When implementing, expose `get_db()` (connection with `row_factory` + foreign keys), `init_db()` (CREATE TABLE IF NOT EXISTS), and `seed_db()`.
- **`templates/`** — Jinja2. Every page extends `base.html`, which defines blocks `title`, `head`, `content`, `scripts`. The footer (with terms/privacy links) and nav live in `base.html` — don't duplicate them into page templates.
- **`static/css/style.css`** — the single stylesheet for the whole site. There is no per-page CSS file (e.g. no `landing.css`); page-specific styles either go here or inline in the template's `{% block head %}`.
- **`static/js/main.js`** — globally included from `base.html`. Page-specific JS goes inside a template's `{% block scripts %}` as a vanilla-JS IIFE. The project has no JS framework or bundler — keep it that way.

## Implemented vs stub routes

| Route                          | Status                          |
| ------------------------------ | ------------------------------- |
| `GET /`                        | Implemented — `landing.html`    |
| `GET /register`                | Implemented — `register.html`   |
| `GET /login`                   | Implemented — `login.html`      |
| `GET /terms`                   | Implemented — `terms.html`      |
| `GET /privacy`                 | Implemented — `privacy.html`    |
| `GET /logout`                  | Stub — Step 3                   |
| `GET /profile`                 | Stub — Step 4                   |
| `GET /expenses/add`            | Stub — Step 7                   |
| `GET /expenses/<id>/edit`      | Stub — Step 8                   |
| `GET /expenses/<id>/delete`    | Stub — Step 9                   |

Do not implement a stub route unless the active task explicitly targets that step.

## Where things belong

- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` only, never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → new `.css` file, not inline `<style>` tags

## Code style

- **Python:** PEP 8, snake_case for all variables and functions
- **Templates:** Jinja2 with `url_for()` for every internal link — never hardcode URLs
- **Route functions:** one responsibility only — fetch data, render template, done
- **DB queries:** always use parameterized queries (`?` placeholders) — never f-strings in SQL
- **Error handling:** use `abort()` for HTTP errors, not bare `return "error string"`

## Tech constraints

- Flask only — no FastAPI, no Django, no other web frameworks
- SQLite only — no PostgreSQL, no SQLAlchemy ORM, no external DB
- Vanilla JS only — no React, no jQuery, no npm packages
- No new pip packages — work within `requirements.txt` as-is unless explicitly told otherwise
- Python 3.10+ assumed — f-strings and `match` statements are fine

## Conventions

- Theme uses CSS variables defined in `style.css` (`--ink`, `--paper`, `--accent`, `--accent-2`, `--border`, etc.) and the font pair DM Serif Display (headings) + DM Sans (body) loaded in `base.html`. New components should reuse these tokens, not hardcode colors.
- Currency is rendered as `₹` (INR) throughout copy.
- When the user says "modify only X, don't touch other parts," scope edits tightly — this preference has come up repeatedly.

## Subagent policy

- Always use the built-in **Explore** subagent for codebase exploration before implementing any new feature
- Always use a subagent to verify test results after any implementation
- When asked to plan, delegate codebase research to a subagent before presenting the plan
- Always use the built-in **Plan** subagent in plan mode

## Warnings and things to avoid

- Never use raw string returns for stub routes once a step is implemented — always render a template
- Never hardcode URLs in templates — always use `url_for()`
- Never put DB logic in route functions — it belongs in `database/db.py`
- Never install new packages mid-feature without flagging it — keep `requirements.txt` in sync
- Never use JS frameworks — the frontend is intentionally vanilla
- `database/db.py` is currently empty — do not assume helpers exist until the step that implements them
- FK enforcement is manual — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- The app runs on port **5001**, not the Flask default 5000 — don't change this
