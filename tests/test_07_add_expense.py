"""
Tests for Step 7 — Add Expense feature at /expenses/add.

Coverage:
  Part 1  — Auth / access control: unauthenticated GET and POST redirect to
             /login and never insert data.
  Part 2  — GET happy path: 200, correct heading, today's date pre-filled,
             all 7 CATEGORIES present, no error block, ₹ symbol rendered,
             submit button present.
  Part 3  — POST happy path: valid submission inserts exactly one row, all
             field values match, row belongs to session user, redirect is 302
             to /profile, and /profile shows the updated total and count.
  Part 4  — Amount validation (parametrized): blank, non-numeric, zero,
             negative, over-cap all return HTTP 200 with an inline error and
             insert nothing.
  Part 5  — Category validation: a value not in CATEGORIES returns HTTP 200
             with an error and inserts nothing.
  Part 6  — Date validation (parametrized): unparseable, future, and blank
             dates return HTTP 200 with an error and insert nothing.  A
             boundary test confirms today's date is accepted.
  Part 7  — Description handling: blank and whitespace-only descriptions are
             stored as NULL; a 250-character description is truncated to 200
             characters (not rejected); the row is always inserted.
  Part 8  — Form re-render preserves typed values: after any validation
             error the response echoes back amount, category, date, and
             description via the form's value= / selected attributes.
  Part 9  — No-side-effects (parametrized): every validation-failure path
             leaves the expense count for the test user unchanged.
  Part 10 — User-ID integrity: a user_id field in the POST body is ignored;
             the inserted row always belongs to the session user.

Isolation: every test uses the `tmp_db` fixture from conftest.py, which
monkeypatches database.db.DB_PATH to a per-test temp file.  The production
spendly.db is never touched.
"""

from datetime import date

import pytest

import database.db
from database.db import CATEGORIES

# ---------------------------------------------------------------------------
# Module-level helpers: open a connection to the monkeypatched temp DB
# ---------------------------------------------------------------------------

def _count_expenses(user_id):
    """Return the number of expense rows for *user_id* in the current temp DB."""
    conn = database.db.get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def _get_expenses(user_id):
    """Return all expense rows for *user_id* ordered newest-inserted first."""
    conn = database.db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Part 1: Auth / access control
# ---------------------------------------------------------------------------


class TestAddExpenseAuthGuard:
    """Unauthenticated requests must redirect to /login and never write to the DB."""

    def test_get_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/add", follow_redirects=False)
        assert resp.status_code == 302, (
            "Unauthenticated GET /expenses/add must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect target for unauthenticated GET must be /login"
        )

    def test_post_unauthenticated_redirects_to_login(self, client):
        today = date.today().isoformat()
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Unauthenticated POST /expenses/add must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated POST must redirect to /login"
        )

    def test_post_unauthenticated_no_row_inserted(self, client, tmp_db):
        initial_count = _count_expenses(tmp_db["user_id"])
        today = date.today().isoformat()
        client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        assert _count_expenses(tmp_db["user_id"]) == initial_count, (
            "Unauthenticated POST must not insert any row into the expenses table"
        )


# ---------------------------------------------------------------------------
# Part 2: GET /expenses/add — happy path
# ---------------------------------------------------------------------------


class TestAddExpenseGet:
    """Authenticated GET /expenses/add must render the form correctly."""

    def test_get_authenticated_returns_200(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200, (
            "Authenticated GET /expenses/add must return HTTP 200"
        )

    def test_get_renders_add_expense_heading(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert b"Add expense" in resp.data, (
            "The response must contain the 'Add expense' heading"
        )

    def test_get_date_input_prefilled_with_today(self, auth_client):
        today = date.today().isoformat()
        resp = auth_client.get("/expenses/add")
        assert today.encode() in resp.data, (
            f"The date input must be pre-filled with today's date ({today})"
        )

    def test_get_all_7_categories_present_in_select(self, auth_client):
        resp = auth_client.get("/expenses/add")
        for cat in CATEGORIES:
            assert cat.encode() in resp.data, (
                f"Category '{cat}' must appear in the category <select> on a fresh GET"
            )

    def test_get_no_error_block_on_fresh_load(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert b"form-error" not in resp.data, (
            "No form-error block should be rendered on a fresh GET of /expenses/add"
        )

    def test_get_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert "₹".encode("utf-8") in resp.data, (
            "The add-expense form must render the ₹ (INR) symbol, not a different currency"
        )

    def test_get_submit_button_present(self, auth_client):
        resp = auth_client.get("/expenses/add")
        # Spec says the submit button is labelled "Add expense".
        assert b"Add expense" in resp.data, (
            "A submit button labelled 'Add expense' must be present on the form"
        )


# ---------------------------------------------------------------------------
# Part 3: POST /expenses/add — happy path
# ---------------------------------------------------------------------------


class TestAddExpensePostHappyPath:
    """A valid POST must insert exactly one row and redirect (302) to /profile."""

    def test_post_valid_returns_302_redirect(self, auth_client):
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "A valid POST must return HTTP 302"
        )

    def test_post_valid_redirects_to_profile(self, auth_client):
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        assert "/profile" in resp.headers["Location"], (
            "A successful add must redirect to /profile (PRG pattern)"
        )

    def test_post_valid_inserts_exactly_one_row(self, auth_client, tmp_db):
        initial_count = _count_expenses(tmp_db["user_id"])
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        assert _count_expenses(tmp_db["user_id"]) == initial_count + 1, (
            "A valid POST must insert exactly one new expense row"
        )

    def test_post_valid_row_has_correct_amount(self, auth_client, tmp_db):
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        rows = _get_expenses(tmp_db["user_id"])
        assert float(rows[0]["amount"]) == pytest.approx(125.50), (
            "The inserted amount must match the submitted value"
        )

    def test_post_valid_row_has_correct_category_and_date(self, auth_client, tmp_db):
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        rows = _get_expenses(tmp_db["user_id"])
        assert rows[0]["category"] == "Food", (
            "The inserted category must match the submitted value"
        )
        assert rows[0]["date"] == today, (
            "The inserted date must match the submitted value"
        )

    def test_post_valid_row_has_correct_description(self, auth_client, tmp_db):
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        rows = _get_expenses(tmp_db["user_id"])
        assert rows[0]["description"] == "Lunch", (
            "The inserted description must match the submitted value"
        )

    def test_post_valid_row_belongs_to_session_user(self, auth_client, tmp_db):
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "Transport",
                "date": today,
                "description": "Taxi",
            },
            follow_redirects=False,
        )
        rows = _get_expenses(tmp_db["user_id"])
        assert rows[0]["user_id"] == tmp_db["user_id"], (
            "The inserted expense must be associated with the logged-in user's ID"
        )

    def test_post_valid_profile_shows_updated_total(self, auth_client, tmp_db):
        """After insert, GET /profile must reflect the new cumulative total."""
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        # Existing seed total is 650.00; adding 125.50 yields 775.50.
        resp = auth_client.get("/profile")
        assert b"775" in resp.data, (
            "After adding an expense of 125.50, /profile must display the updated total (775.50)"
        )

    def test_post_valid_profile_shows_incremented_transaction_count(self, auth_client, tmp_db):
        """After insert, GET /profile must show count incremented by one."""
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "125.50",
                "category": "Food",
                "date": today,
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        expected_count = str(tmp_db["all_time_count"] + 1).encode()
        resp = auth_client.get("/profile")
        assert expected_count in resp.data, (
            f"After inserting one expense, /profile must show transaction count {tmp_db['all_time_count'] + 1}"
        )


# ---------------------------------------------------------------------------
# Part 4: Amount validation
# ---------------------------------------------------------------------------


class TestAddExpenseAmountValidation:
    """
    Invalid amounts must return HTTP 200 with an inline error message and
    must not insert any row into the expenses table.
    """

    @pytest.mark.parametrize("bad_amount", [
        "",            # blank
        "abc",         # non-numeric
        "0",           # exactly zero (not > 0)
        "-5",          # negative
        "9999999999",  # over the 9_999_999.99 cap
    ])
    def test_invalid_amount_returns_200(self, auth_client, bad_amount):
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": today,
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
    def test_invalid_amount_renders_error_message(self, auth_client, bad_amount):
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": today,
                "description": "Test",
            },
            follow_redirects=False,
        )
        # The spec requires a single inline error message on re-render.
        assert b"form-error" in resp.data or b"error" in resp.data.lower(), (
            f"amount={bad_amount!r} must render an inline error message"
        )

    @pytest.mark.parametrize("bad_amount", [
        "",
        "abc",
        "0",
        "-5",
        "9999999999",
    ])
    def test_invalid_amount_no_row_inserted(self, auth_client, tmp_db, bad_amount):
        initial_count = _count_expenses(tmp_db["user_id"])
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": today,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert _count_expenses(tmp_db["user_id"]) == initial_count, (
            f"amount={bad_amount!r} must NOT insert any row into the expenses table"
        )


# ---------------------------------------------------------------------------
# Part 5: Category validation
# ---------------------------------------------------------------------------


class TestAddExpenseCategoryValidation:
    """A category value absent from CATEGORIES must be rejected without inserting a row."""

    def test_invalid_category_returns_200(self, auth_client):
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": today,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            "A category not in CATEGORIES must re-render the form (HTTP 200)"
        )

    def test_invalid_category_renders_error_message(self, auth_client):
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": today,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert b"form-error" in resp.data or b"error" in resp.data.lower(), (
            "A tampered category value must render an inline error message"
        )

    def test_invalid_category_no_row_inserted(self, auth_client, tmp_db):
        initial_count = _count_expenses(tmp_db["user_id"])
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": today,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert _count_expenses(tmp_db["user_id"]) == initial_count, (
            "An invalid category must NOT insert any row into the expenses table"
        )


# ---------------------------------------------------------------------------
# Part 6: Date validation
# ---------------------------------------------------------------------------


class TestAddExpenseDateValidation:
    """Invalid or future dates must return HTTP 200 with an error and insert nothing."""

    @pytest.mark.parametrize("bad_date,label", [
        ("banana",     "unparseable string"),
        ("2099-01-01", "future date"),
        ("",           "blank"),
    ])
    def test_invalid_date_returns_200(self, auth_client, bad_date, label):
        resp = auth_client.post(
            "/expenses/add",
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
        ("banana",     "unparseable string"),
        ("2099-01-01", "future date"),
        ("",           "blank"),
    ])
    def test_invalid_date_renders_error_message(self, auth_client, bad_date, label):
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": bad_date,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert b"form-error" in resp.data or b"error" in resp.data.lower(), (
            f"date={bad_date!r} ({label}) must render an inline error message"
        )

    @pytest.mark.parametrize("bad_date,label", [
        ("banana",     "unparseable string"),
        ("2099-01-01", "future date"),
        ("",           "blank"),
    ])
    def test_invalid_date_no_row_inserted(self, auth_client, tmp_db, bad_date, label):
        initial_count = _count_expenses(tmp_db["user_id"])
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": bad_date,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert _count_expenses(tmp_db["user_id"]) == initial_count, (
            f"date={bad_date!r} ({label}) must NOT insert any row into the expenses table"
        )

    def test_today_date_is_accepted_not_treated_as_future(self, auth_client, tmp_db):
        """The boundary: today's date is NOT in the future and must be accepted."""
        today = date.today().isoformat()
        initial_count = _count_expenses(tmp_db["user_id"])
        resp = auth_client.post(
            "/expenses/add",
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
        assert _count_expenses(tmp_db["user_id"]) == initial_count + 1, (
            "A POST with today's date must insert one row"
        )


# ---------------------------------------------------------------------------
# Part 7: Description handling
# ---------------------------------------------------------------------------


class TestAddExpenseDescriptionHandling:
    """
    Blank / whitespace-only descriptions are stored as NULL.
    Descriptions longer than 200 characters are truncated to exactly 200.
    """

    def test_blank_description_stores_null(self, auth_client, tmp_db):
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": today,
                "description": "",
            },
            follow_redirects=False,
        )
        rows = _get_expenses(tmp_db["user_id"])
        assert rows[0]["description"] is None, (
            "A blank description must be stored as NULL, not as an empty string"
        )

    def test_whitespace_only_description_stores_null(self, auth_client, tmp_db):
        today = date.today().isoformat()
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": today,
                "description": "   ",
            },
            follow_redirects=False,
        )
        rows = _get_expenses(tmp_db["user_id"])
        assert rows[0]["description"] is None, (
            "A whitespace-only description must be stored as NULL after trimming"
        )

    def test_long_description_is_truncated_to_200_chars(self, auth_client, tmp_db):
        today = date.today().isoformat()
        long_desc = "X" * 250  # 50 chars over the 200-char cap
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": today,
                "description": long_desc,
            },
            follow_redirects=False,
        )
        rows = _get_expenses(tmp_db["user_id"])
        stored = rows[0]["description"]
        assert stored is not None, (
            "A non-blank long description must be stored (not discarded as NULL)"
        )
        assert len(stored) == 200, (
            f"A 250-char description must be truncated to exactly 200 chars; got {len(stored)}"
        )

    def test_long_description_still_inserts_row(self, auth_client, tmp_db):
        """A description over 200 chars must cause a truncation, not a rejection."""
        today = date.today().isoformat()
        initial_count = _count_expenses(tmp_db["user_id"])
        long_desc = "A" * 250
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "30.00",
                "category": "Food",
                "date": today,
                "description": long_desc,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "A long description must not cause a validation error — it is truncated and the expense is inserted"
        )
        assert _count_expenses(tmp_db["user_id"]) == initial_count + 1, (
            "A POST with a long description must insert one row (after truncation)"
        )


# ---------------------------------------------------------------------------
# Part 8: Form re-render preserves typed values after a validation error
# ---------------------------------------------------------------------------


class TestAddExpenseFormPreservesValues:
    """
    When a POST fails validation the re-rendered form must echo back every
    field the user typed (amount, category, date, description).
    """

    def test_preserves_amount_after_category_error(self, auth_client):
        """Typed amount must survive a category-validation error."""
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "99.99",
                "category": "NotACategory",
                "date": today,
                "description": "My lunch",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"99.99" in resp.data, (
            "The typed amount (99.99) must be echoed back in the form after a category error"
        )

    def test_preserves_category_after_amount_error(self, auth_client):
        """Typed category must survive an amount-validation error."""
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Health",
                "date": today,
                "description": "Doctor visit",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"Health" in resp.data, (
            "The typed category (Health) must appear in the form after an amount error"
        )

    def test_preserves_date_after_category_error(self, auth_client):
        """Typed date must survive a category-validation error."""
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": today,
                "description": "Test",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert today.encode() in resp.data, (
            "The typed date must be echoed back in the form after a category error"
        )

    def test_preserves_description_after_category_error(self, auth_client):
        """Typed description must survive a category-validation error."""
        today = date.today().isoformat()
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "50.00",
                "category": "NotACategory",
                "date": today,
                "description": "My lunch",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert b"My lunch" in resp.data, (
            "The typed description must be echoed back in the form after a category error"
        )

    def test_all_fields_preserved_simultaneously(self, auth_client):
        """All four fields must be present in a single error-response."""
        today = date.today().isoformat()
        # Use a valid category but invalid amount so we get a clean error
        # while checking category, date, and description preservation.
        resp = auth_client.post(
            "/expenses/add",
            data={
                "amount": "0",               # invalid (zero)
                "category": "Entertainment", # valid — should be preserved / selected
                "date": today,              # valid — should be preserved
                "description": "Cinema tickets",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200, "Validation error must re-render the form"
        assert b"Entertainment" in resp.data, "Category must be preserved after amount error"
        assert today.encode() in resp.data, "Date must be preserved after amount error"
        assert b"Cinema tickets" in resp.data, "Description must be preserved after amount error"


# ---------------------------------------------------------------------------
# Part 9: No-side-effects — every failure path leaves the DB unchanged
# ---------------------------------------------------------------------------


class TestAddExpenseNoSideEffects:
    """
    Each validation-failure path must leave the expenses count for the test
    user exactly as it was before the POST.
    """

    @pytest.mark.parametrize("form_data,label", [
        (
            {"amount": "",        "category": "Food",         "date": "2020-01-01", "description": "Test"},
            "blank amount",
        ),
        (
            {"amount": "abc",     "category": "Food",         "date": "2020-01-01", "description": "Test"},
            "non-numeric amount",
        ),
        (
            {"amount": "0",       "category": "Food",         "date": "2020-01-01", "description": "Test"},
            "zero amount",
        ),
        (
            {"amount": "-5",      "category": "Food",         "date": "2020-01-01", "description": "Test"},
            "negative amount",
        ),
        (
            {"amount": "50.00",   "category": "NotACategory", "date": "2020-01-01", "description": "Test"},
            "invalid category",
        ),
        (
            {"amount": "50.00",   "category": "Food",         "date": "banana",     "description": "Test"},
            "unparseable date",
        ),
        (
            {"amount": "50.00",   "category": "Food",         "date": "2099-01-01", "description": "Test"},
            "future date",
        ),
        (
            {"amount": "50.00",   "category": "Food",         "date": "",           "description": "Test"},
            "blank date",
        ),
    ])
    def test_failed_post_does_not_insert_row(self, auth_client, tmp_db, form_data, label):
        initial_count = _count_expenses(tmp_db["user_id"])
        auth_client.post("/expenses/add", data=form_data, follow_redirects=False)
        assert _count_expenses(tmp_db["user_id"]) == initial_count, (
            f"A POST with {label} must not insert any row — expense count must remain {initial_count}"
        )


# ---------------------------------------------------------------------------
# Part 10: User-ID integrity — session user_id, never the form field
# ---------------------------------------------------------------------------


class TestAddExpenseUserIdIntegrity:
    """
    The route must read user_id exclusively from the session.
    A user_id value submitted in the POST body must be silently ignored.
    """

    def test_form_user_id_field_is_ignored(self, auth_client, tmp_db):
        """
        Even if an attacker injects user_id=<other_user> into the form body,
        the inserted row must belong to the authenticated session user.
        """
        # Create a second user directly in the temp DB (no need to log in as them).
        conn = database.db.get_db()
        try:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Other User", "other@example.com", "irrelevant-hash"),
            )
            other_user_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        today = date.today().isoformat()
        # POST as the legitimate session user but include a spoofed user_id field.
        auth_client.post(
            "/expenses/add",
            data={
                "amount": "200.00",
                "category": "Other",
                "date": today,
                "description": "Spoofed ownership attempt",
                "user_id": str(other_user_id),  # attacker-supplied value
            },
            follow_redirects=False,
        )

        # The newly inserted row must belong to the session user, not other_user_id.
        session_user_rows = _get_expenses(tmp_db["user_id"])
        assert session_user_rows[0]["user_id"] == tmp_db["user_id"], (
            "The inserted row's user_id must match the session user, not the form-supplied user_id"
        )

        # No row must have been inserted for the second user.
        conn = database.db.get_db()
        try:
            other_count = conn.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
                (other_user_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        assert other_count == 0, (
            "No expense must be inserted for the other user when user_id is injected via the form body"
        )
