"""
Tests for Step 8 — Edit Expense feature at /expenses/<int:id>/edit.

Coverage:
  Part 1  — Auth / access control: unauthenticated GET and POST redirect to
             /login and never mutate the row.
  Part 2  — Ownership / 404 semantics: non-existent id and another user's id
             both return 404 on GET and POST; a cross-user POST must not mutate
             the target row.
  Part 3  — GET happy path: authenticated owner sees 200, "Edit expense"
             heading, form pre-filled with the row's current amount/category/
             date/description, ₹ symbol present, all 7 CATEGORIES rendered,
             "Save changes" submit button, and no error block on fresh load.
  Part 4  — POST happy path: valid submission updates the row in the DB,
             redirects (302) to /profile, and the updated total appears on
             /profile.
  Part 5  — Amount validation (parametrized): blank, non-numeric, zero,
             negative, over-cap → HTTP 200 with an inline error, no mutation.
  Part 6  — Category validation: value outside CATEGORIES → HTTP 200 with an
             error, no mutation.
  Part 7  — Date validation (parametrized): blank, unparseable, future date
             → HTTP 200 with an error, no mutation. Today's date IS accepted.
  Part 8  — Description handling: blank and whitespace-only stored as NULL;
             a 250-char description truncated to exactly 200 chars (not
             rejected — the edit still succeeds with a 302).
  Part 9  — CSRF: missing or wrong csrf_token does not mutate the row and
             redirects back to the same /expenses/<id>/edit URL.
  Part 10 — Form re-render preserves SUBMITTED values (not DB values) after a
             validation error — amount, category, date, description.
  Part 11 — Profile edit links: GET /profile renders an edit link per
             transaction row pointing at the correct /expenses/<id>/edit URL.

Isolation: every test uses the `tmp_db` fixture from conftest.py, which
monkeypatches database.db.DB_PATH to a per-test temp file. The production
spendly.db is never touched.

conftest seed (TEST_EXPENSES — in insertion order, row 0 used throughout):
  0: (300.00, "Bills",     "2026-01-01", "Old electricity bill")
  1: (100.00, "Food",      "2026-06-01", "June groceries")
  2: ( 50.00, "Food",      "2026-06-10", "June snacks")
  3: (200.00, "Transport", "2026-06-15", "June taxi")
  All-time total: 650.00
"""

from datetime import date

import pytest

import database.db
from database.db import CATEGORIES


# ---------------------------------------------------------------------------
# Module-level helpers — open the monkeypatched temp DB directly
# ---------------------------------------------------------------------------

def _get_expense(expense_id):
    """Fetch a single expense row by id (no user filter) for mutation checks."""
    conn = database.db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()
    finally:
        conn.close()


def _all_expense_ids(user_id):
    """Return all expense IDs for user_id ordered by id ASC."""
    conn = database.db.get_db()
    try:
        rows = conn.execute(
            "SELECT id FROM expenses WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [row["id"] for row in rows]


def _first_expense_id(user_id):
    """Return the id of the lowest-id expense for user_id (TEST_EXPENSES[0])."""
    return _all_expense_ids(user_id)[0]


def _seed_other_user_expense():
    """Insert a second user with one expense. Returns (other_user_id, other_expense_id)."""
    conn = database.db.get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other User", "other@example.com", "irrelevant-hash"),
        )
        other_user_id = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (other_user_id, 42.00, "Food", "2026-06-05", "Other user meal"),
        )
        other_expense_id = cursor.lastrowid
        conn.commit()
        return other_user_id, other_expense_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Part 1: Auth / access control
# ---------------------------------------------------------------------------


class TestEditExpenseAuthGuard:
    """Unauthenticated requests must redirect to /login and never mutate the row."""

    def test_get_unauthenticated_redirects_to_login(self, client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = client.get(f"/expenses/{expense_id}/edit", follow_redirects=False)
        assert resp.status_code == 302, (
            "Unauthenticated GET /expenses/<id>/edit must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect target for unauthenticated GET must be /login"
        )

    def test_post_unauthenticated_redirects_to_login(self, client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "hacked",
                "csrf_token": "any",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Unauthenticated POST /expenses/<id>/edit must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated POST must redirect to /login"
        )

    def test_post_unauthenticated_does_not_mutate_amount(self, client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        original = _get_expense(expense_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "hacked",
                "csrf_token": "any",
            },
            follow_redirects=False,
        )
        after = _get_expense(expense_id)
        assert after["amount"] == original["amount"], (
            "Unauthenticated POST must not update the expense amount"
        )

    def test_post_unauthenticated_does_not_mutate_category(self, client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        original = _get_expense(expense_id)
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "hacked",
                "csrf_token": "any",
            },
            follow_redirects=False,
        )
        after = _get_expense(expense_id)
        assert after["category"] == original["category"], (
            "Unauthenticated POST must not update the expense category"
        )


# ---------------------------------------------------------------------------
# Part 2: Ownership / 404 semantics
# ---------------------------------------------------------------------------


class TestEditExpenseOwnership:
    """Non-existent id and another user's id return 404; cross-user POST must not mutate."""

    def test_get_nonexistent_id_returns_404(self, auth_client):
        resp = auth_client.get("/expenses/999999/edit", follow_redirects=False)
        assert resp.status_code == 404, (
            "GET /expenses/<nonexistent_id>/edit must return 404"
        )

    def test_post_nonexistent_id_returns_404(self, auth_client):
        resp = auth_client.post(
            "/expenses/999999/edit",
            data={
                "amount": "100.00",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "ghost row",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 404, (
            "POST /expenses/<nonexistent_id>/edit must return 404"
        )

    def test_get_other_users_expense_returns_404(self, auth_client, tmp_db):
        """Expense belonging to a different user must yield 404, not the form."""
        _, other_expense_id = _seed_other_user_expense()
        resp = auth_client.get(
            f"/expenses/{other_expense_id}/edit",
            follow_redirects=False,
        )
        assert resp.status_code == 404, (
            "GET /expenses/<other_user_expense>/edit must return 404 "
            "(not 403, not the form — existence must not be leaked)"
        )

    def test_post_other_users_expense_returns_404(self, auth_client, tmp_db):
        """POST targeting another user's expense must 404 before any write."""
        _, other_expense_id = _seed_other_user_expense()
        resp = auth_client.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "cross-user tamper",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 404, (
            "POST /expenses/<other_user_expense>/edit must return 404"
        )

    def test_post_other_users_expense_does_not_mutate_amount(self, auth_client, tmp_db):
        _, other_expense_id = _seed_other_user_expense()
        original = _get_expense(other_expense_id)
        auth_client.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "cross-user tamper",
            },
            follow_redirects=False,
        )
        after = _get_expense(other_expense_id)
        assert after["amount"] == original["amount"], (
            "POST targeting another user's expense must not update the amount"
        )

    def test_post_other_users_expense_does_not_mutate_category(self, auth_client, tmp_db):
        _, other_expense_id = _seed_other_user_expense()
        original = _get_expense(other_expense_id)
        auth_client.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "cross-user tamper",
            },
            follow_redirects=False,
        )
        after = _get_expense(other_expense_id)
        assert after["category"] == original["category"], (
            "POST targeting another user's expense must not update the category"
        )


# ---------------------------------------------------------------------------
# Part 3: GET happy path
# ---------------------------------------------------------------------------


class TestEditExpenseGet:
    """Authenticated owner sees the form pre-filled with the row's current values."""

    def test_get_authenticated_returns_200(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit", follow_redirects=False)
        assert resp.status_code == 200, (
            "Authenticated GET /expenses/<id>/edit must return HTTP 200"
        )

    def test_get_renders_edit_expense_heading(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        assert b"Edit expense" in resp.data, (
            "The response must contain an 'Edit expense' heading"
        )

    def test_get_prefills_amount(self, auth_client, tmp_db):
        """Amount input must be pre-filled with the row's current amount (300.00)."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        # TEST_EXPENSES[0] amount = 300.00, rendered as "300.00"
        assert b"300.00" in resp.data, (
            "The amount input must be pre-filled with the expense's current amount (300.00)"
        )

    def test_get_prefills_category(self, auth_client, tmp_db):
        """Category select must reflect the row's current category (Bills)."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        # TEST_EXPENSES[0] category = "Bills"
        assert b"Bills" in resp.data, (
            "The category select must contain the expense's current category (Bills)"
        )

    def test_get_prefills_date(self, auth_client, tmp_db):
        """Date input must be pre-filled with the row's date in YYYY-MM-DD format."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        # TEST_EXPENSES[0] date = "2026-01-01"
        assert b"2026-01-01" in resp.data, (
            "The date input must be pre-filled with the expense's current date (2026-01-01)"
        )

    def test_get_prefills_description(self, auth_client, tmp_db):
        """Description input must contain the row's current description text."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        # TEST_EXPENSES[0] description = "Old electricity bill"
        assert b"Old electricity bill" in resp.data, (
            "The description input must be pre-filled with the expense's current description"
        )

    def test_get_rupee_symbol_present(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        assert "₹".encode("utf-8") in resp.data, (
            "The edit-expense form must render the ₹ (INR) symbol, not a different currency"
        )

    def test_get_all_7_categories_rendered(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        for cat in CATEGORIES:
            assert cat.encode() in resp.data, (
                f"Category '{cat}' must appear in the category <select> on the edit form"
            )

    def test_get_save_changes_button_present(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        assert b"Save changes" in resp.data, (
            "A submit button labelled 'Save changes' must be present on the edit form"
        )

    def test_get_no_error_block_on_fresh_load(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.get(f"/expenses/{expense_id}/edit")
        assert b"form-error" not in resp.data, (
            "No error block must be rendered on a fresh GET of the edit form"
        )


# ---------------------------------------------------------------------------
# Part 4: POST happy path
# ---------------------------------------------------------------------------


class TestEditExpensePostHappyPath:
    """A valid POST must update the row in the DB and redirect (302) to /profile."""

    def test_post_valid_returns_302(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "555.55",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Updated meal",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "A valid POST to /expenses/<id>/edit must return HTTP 302"
        )

    def test_post_valid_redirects_to_profile(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "555.55",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Updated meal",
            },
            follow_redirects=False,
        )
        assert "/profile" in resp.headers["Location"], (
            "A successful edit must redirect to /profile (PRG pattern)"
        )

    def test_post_valid_updates_amount_in_db(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "555.55",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Updated meal",
            },
            follow_redirects=False,
        )
        assert float(_get_expense(expense_id)["amount"]) == pytest.approx(555.55), (
            "The updated amount must be persisted to the DB"
        )

    def test_post_valid_updates_category_in_db(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "555.55",
                "category": "Health",
                "date": date.today().isoformat(),
                "description": "Updated meal",
            },
            follow_redirects=False,
        )
        assert _get_expense(expense_id)["category"] == "Health", (
            "The updated category must be persisted to the DB"
        )

    def test_post_valid_updates_date_in_db(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        today = date.today().isoformat()
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "555.55",
                "category": "Food",
                "date": today,
                "description": "Updated meal",
            },
            follow_redirects=False,
        )
        assert _get_expense(expense_id)["date"] == today, (
            "The updated date must be persisted to the DB"
        )

    def test_post_valid_updates_description_in_db(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "555.55",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Updated meal",
            },
            follow_redirects=False,
        )
        assert _get_expense(expense_id)["description"] == "Updated meal", (
            "The updated description must be persisted to the DB"
        )

    def test_post_valid_does_not_change_owner(self, auth_client, tmp_db):
        """A successful edit must not alter the user_id of the row."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "555.55",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Updated meal",
            },
            follow_redirects=False,
        )
        assert _get_expense(expense_id)["user_id"] == tmp_db["user_id"], (
            "A valid edit must not change the expense's user_id"
        )

    def test_post_valid_profile_shows_updated_total(self, auth_client, tmp_db):
        """
        Seed total is 650.00 (300+100+50+200).  Changing the 300.00 row to
        100.00 gives 100+100+50+200 = 450.00.  /profile must display 450.
        """
        expense_id = _first_expense_id(tmp_db["user_id"])  # Bills row (300.00)
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "100.00",
                "category": "Bills",
                "date": "2026-01-01",
                "description": "Old electricity bill",
            },
            follow_redirects=False,
        )
        resp = auth_client.get("/profile")
        assert b"450" in resp.data, (
            "After editing the 300.00 expense to 100.00, /profile must display the updated total (450.00)"
        )


# ---------------------------------------------------------------------------
# Part 5: Amount validation
# ---------------------------------------------------------------------------


class TestEditExpenseAmountValidation:
    """
    Invalid amounts must return HTTP 200 with an inline error and must not
    mutate the DB row.
    """

    @pytest.mark.parametrize("bad_amount", [
        "",            # blank
        "abc",         # non-numeric
        "0",           # exactly zero (not > 0)
        "-5",          # negative
        "9999999999",  # over the 9_999_999.99 cap
    ])
    def test_invalid_amount_returns_200(self, auth_client, tmp_db, bad_amount):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"amount={bad_amount!r} must re-render the form (HTTP 200), not redirect"
        )

    @pytest.mark.parametrize("bad_amount", [
        "",
        "abc",
        "0",
        "-5",
        "9999999999",
    ])
    def test_invalid_amount_renders_error_message(self, auth_client, tmp_db, bad_amount):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Test",
            },
            follow_redirects=False,
        )
        # Accept either the CSS class sentinel or any case-insensitive "error" text.
        body = resp.data
        assert b"form-error" in body or b"error" in body.lower(), (
            f"amount={bad_amount!r} must render an inline error message"
        )

    @pytest.mark.parametrize("bad_amount", [
        "",
        "abc",
        "0",
        "-5",
        "9999999999",
    ])
    def test_invalid_amount_does_not_mutate_row(self, auth_client, tmp_db, bad_amount):
        expense_id = _first_expense_id(tmp_db["user_id"])
        original = _get_expense(expense_id)
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "Test",
            },
            follow_redirects=False,
        )
        after = _get_expense(expense_id)
        assert after["amount"] == original["amount"], (
            f"amount={bad_amount!r} must NOT update the expense amount in the DB"
        )
        assert after["category"] == original["category"], (
            f"amount={bad_amount!r} must NOT update the expense category in the DB"
        )
        assert after["date"] == original["date"], (
            f"amount={bad_amount!r} must NOT update the expense date in the DB"
        )


# ---------------------------------------------------------------------------
# Part 6: Category validation
# ---------------------------------------------------------------------------


class TestEditExpenseCategoryValidation:
    """A category value absent from CATEGORIES must be rejected without mutating the row."""

    def test_invalid_category_returns_200(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": date.today().isoformat(),
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            "A category not in CATEGORIES must re-render the form (HTTP 200)"
        )

    def test_invalid_category_renders_error_message(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": date.today().isoformat(),
                "description": "Test",
            },
            follow_redirects=False,
        )
        body = resp.data
        assert b"form-error" in body or b"error" in body.lower(), (
            "A tampered category value must render an inline error message"
        )

    def test_invalid_category_does_not_mutate_row(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        original = _get_expense(expense_id)
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": date.today().isoformat(),
                "description": "Test",
            },
            follow_redirects=False,
        )
        after = _get_expense(expense_id)
        assert after["category"] == original["category"], (
            "An invalid category must NOT update the expense category in the DB"
        )
        assert after["amount"] == original["amount"], (
            "An invalid category must NOT update the expense amount in the DB"
        )


# ---------------------------------------------------------------------------
# Part 7: Date validation
# ---------------------------------------------------------------------------


class TestEditExpenseDateValidation:
    """Invalid or future dates must return HTTP 200 with an error and no mutation."""

    @pytest.mark.parametrize("bad_date,label", [
        ("",           "blank"),
        ("banana",     "unparseable string"),
        ("2099-01-01", "future date"),
    ])
    def test_invalid_date_returns_200(self, auth_client, tmp_db, bad_date, label):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": bad_date,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"date={bad_date!r} ({label}) must re-render the form (HTTP 200), not redirect"
        )

    @pytest.mark.parametrize("bad_date,label", [
        ("",           "blank"),
        ("banana",     "unparseable string"),
        ("2099-01-01", "future date"),
    ])
    def test_invalid_date_renders_error_message(self, auth_client, tmp_db, bad_date, label):
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": bad_date,
                "description": "Test",
            },
            follow_redirects=False,
        )
        body = resp.data
        assert b"form-error" in body or b"error" in body.lower(), (
            f"date={bad_date!r} ({label}) must render an inline error message"
        )

    @pytest.mark.parametrize("bad_date,label", [
        ("",           "blank"),
        ("banana",     "unparseable string"),
        ("2099-01-01", "future date"),
    ])
    def test_invalid_date_does_not_mutate_row(self, auth_client, tmp_db, bad_date, label):
        expense_id = _first_expense_id(tmp_db["user_id"])
        original = _get_expense(expense_id)
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": bad_date,
                "description": "Test",
            },
            follow_redirects=False,
        )
        after = _get_expense(expense_id)
        assert after["date"] == original["date"], (
            f"date={bad_date!r} ({label}) must NOT update the expense date in the DB"
        )
        assert after["amount"] == original["amount"], (
            f"date={bad_date!r} ({label}) must NOT update the expense amount in the DB"
        )

    def test_today_date_is_accepted_not_treated_as_future(self, auth_client, tmp_db):
        """Boundary check: today's date is not > date.today() so it must be accepted."""
        today = date.today().isoformat()
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": today,
                "description": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Today's date must be accepted as valid (boundary: not > date.today())"
        )
        assert _get_expense(expense_id)["date"] == today, (
            "A POST with today's date must persist the new date to the DB"
        )


# ---------------------------------------------------------------------------
# Part 8: Description handling
# ---------------------------------------------------------------------------


class TestEditExpenseDescriptionHandling:
    """
    Blank / whitespace-only descriptions are stored as NULL.
    Descriptions longer than 200 characters are truncated to exactly 200 chars
    and the edit still succeeds (302, not a validation error).
    """

    def test_blank_description_stores_null(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "",
            },
            follow_redirects=False,
        )
        assert _get_expense(expense_id)["description"] is None, (
            "A blank description must be stored as NULL, not as an empty string"
        )

    def test_whitespace_only_description_stores_null(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "   ",
            },
            follow_redirects=False,
        )
        assert _get_expense(expense_id)["description"] is None, (
            "A whitespace-only description must be stored as NULL after stripping"
        )

    def test_long_description_truncated_to_200_chars(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        long_desc = "X" * 250  # 50 chars over the 200-char cap
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": long_desc,
            },
            follow_redirects=False,
        )
        stored = _get_expense(expense_id)["description"]
        assert stored is not None, (
            "A non-blank long description must be stored (not discarded as NULL)"
        )
        assert len(stored) == 200, (
            f"A 250-char description must be truncated to exactly 200 chars; got {len(stored)}"
        )

    def test_long_description_does_not_cause_validation_error(self, auth_client, tmp_db):
        """A description over 200 chars must be truncated silently — the edit succeeds."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        long_desc = "A" * 250
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": long_desc,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "A long description must not cause a validation error — the edit succeeds (302)"
        )


# ---------------------------------------------------------------------------
# Part 9: CSRF protection
# ---------------------------------------------------------------------------


class TestEditExpenseCsrf:
    """
    Missing or wrong csrf_token must not mutate the row and must redirect back
    to the same edit URL (not to /profile).
    """

    def test_wrong_csrf_does_not_mutate_row(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        original = _get_expense(expense_id)
        # Explicitly override the auto-injected token with a wrong value.
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "CSRF tamper",
                "csrf_token": "totally-wrong-token",
            },
            follow_redirects=False,
        )
        after = _get_expense(expense_id)
        assert after["amount"] == original["amount"], (
            "A wrong CSRF token must not update the expense amount"
        )
        assert after["category"] == original["category"], (
            "A wrong CSRF token must not update the expense category"
        )

    def test_missing_csrf_does_not_mutate_row(self, auth_client, tmp_db):
        expense_id = _first_expense_id(tmp_db["user_id"])
        original = _get_expense(expense_id)
        # Pass csrf_token="" to suppress the auto-inject and simulate a missing token.
        auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "CSRF missing",
                "csrf_token": "",
            },
            follow_redirects=False,
        )
        after = _get_expense(expense_id)
        assert after["amount"] == original["amount"], (
            "An empty/missing CSRF token must not update the expense amount"
        )

    def test_wrong_csrf_redirects_back_to_edit_url(self, auth_client, tmp_db):
        """Invalid CSRF must redirect to the same edit URL, never to /profile."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "CSRF tamper",
                "csrf_token": "totally-wrong-token",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "An invalid CSRF token must still return 302 (redirect, not 200 error page)"
        )
        location = resp.headers.get("Location", "")
        assert f"/expenses/{expense_id}/edit" in location, (
            "An invalid CSRF token must redirect back to the edit URL, not to /profile"
        )

    def test_missing_csrf_redirects_back_to_edit_url(self, auth_client, tmp_db):
        """Empty CSRF token must redirect to the edit URL, not to /profile."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "999.99",
                "category": "Shopping",
                "date": date.today().isoformat(),
                "description": "CSRF missing",
                "csrf_token": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "A missing CSRF token must return 302"
        )
        location = resp.headers.get("Location", "")
        assert f"/expenses/{expense_id}/edit" in location, (
            "A missing CSRF token must redirect back to the edit URL, not to /profile"
        )


# ---------------------------------------------------------------------------
# Part 10: Form re-render preserves SUBMITTED values (not DB values)
# ---------------------------------------------------------------------------


class TestEditExpenseFormPreservesValues:
    """
    After a validation error, the re-rendered form must echo back the values
    the user submitted — not the current DB values. The seeded first row is:
      (300.00, "Bills", "2026-01-01", "Old electricity bill")
    Tests submit different values with one invalid field and assert the
    submitted values appear in the response.
    """

    def test_preserves_submitted_amount_after_category_error(self, auth_client, tmp_db):
        """Typed amount must survive a category-validation error."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "77.77",          # differs from DB 300.00
                "category": "NotACategory", # invalid — triggers error
                "date": "2026-06-05",
                "description": "Preserved amount test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"77.77" in resp.data, (
            "The submitted amount (77.77) must be echoed back in the form after a category error"
        )

    def test_preserves_submitted_category_after_amount_error(self, auth_client, tmp_db):
        """Typed category must survive an amount-validation error."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "abc",    # invalid — triggers error
                "category": "Health",  # valid but different from DB "Bills"
                "date": "2026-06-05",
                "description": "Doctor visit",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"Health" in resp.data, (
            "The submitted category (Health) must appear in the form after an amount error"
        )

    def test_preserves_submitted_date_after_amount_error(self, auth_client, tmp_db):
        """Typed date must survive an amount-validation error."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "abc",       # invalid — triggers error
                "category": "Food",
                "date": "2026-06-15",  # differs from DB "2026-01-01"
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"2026-06-15" in resp.data, (
            "The submitted date (2026-06-15) must be echoed back after an amount error"
        )

    def test_preserves_submitted_description_after_amount_error(self, auth_client, tmp_db):
        """Typed description must survive an amount-validation error."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "abc",     # invalid — triggers error
                "category": "Food",
                "date": "2026-06-05",
                "description": "My unique note",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"My unique note" in resp.data, (
            "The submitted description must be echoed back after an amount error"
        )

    def test_all_four_fields_preserved_simultaneously(self, auth_client, tmp_db):
        """All four submitted fields must be present in a single error-response."""
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "0",               # invalid (zero) — triggers error
                "category": "Entertainment", # valid — must be preserved
                "date": "2026-06-10",        # valid — must be preserved
                "description": "Cinema tickets",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            "A zero amount must re-render the form (HTTP 200)"
        )
        assert b"Entertainment" in resp.data, (
            "Submitted category must be preserved after an amount error"
        )
        assert b"2026-06-10" in resp.data, (
            "Submitted date must be preserved after an amount error"
        )
        assert b"Cinema tickets" in resp.data, (
            "Submitted description must be preserved after an amount error"
        )

    def test_submitted_amount_overrides_db_value_on_error(self, auth_client, tmp_db):
        """
        On a validation error the form must show the SUBMITTED amount, not
        the DB amount. DB amount is 300.00; submit 88.88 with an invalid
        category — the response must contain 88.88, not the old 300.00.
        """
        expense_id = _first_expense_id(tmp_db["user_id"])
        resp = auth_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "88.88",          # submitted — different from DB 300.00
                "category": "NotACategory", # invalid — triggers error before amount write
                "date": "2026-06-05",
                "description": "Override test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"88.88" in resp.data, (
            "The submitted amount (88.88) must appear in the re-rendered form, "
            "not the DB amount (300.00)"
        )


# ---------------------------------------------------------------------------
# Part 11: Profile page renders edit links per transaction
# ---------------------------------------------------------------------------


class TestProfileEditLinks:
    """
    GET /profile must render an edit link for every transaction row in the
    'Recent transactions' list, each pointing at /expenses/<id>/edit.
    """

    def test_profile_renders_edit_link_for_every_seeded_expense(self, auth_client, tmp_db):
        ids = _all_expense_ids(tmp_db["user_id"])
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
        for expense_id in ids:
            expected_link = f"/expenses/{expense_id}/edit".encode()
            assert expected_link in resp.data, (
                f"The profile page must render an edit link for expense id={expense_id}"
            )

    def test_profile_edit_link_url_contains_expense_id(self, auth_client, tmp_db):
        """Each edit link must embed the specific expense id in the path."""
        ids = _all_expense_ids(tmp_db["user_id"])
        resp = auth_client.get("/profile")
        # Spot-check the first expense
        first_id = ids[0]
        assert f"/expenses/{first_id}/edit".encode() in resp.data, (
            f"The profile page must include /expenses/{first_id}/edit in the HTML"
        )
