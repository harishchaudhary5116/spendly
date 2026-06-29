"""
Shared pytest fixtures for the Spendly test suite.

Isolation strategy: monkeypatch database.db.DB_PATH to a per-test temp file
so that every get_db() call during a test writes to an in-process SQLite
file that is discarded afterwards. The production spendly.db is never touched
during test execution.
"""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

import database.db  # imported for monkeypatching DB_PATH
from app import app as flask_app
from database.db import init_db

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

TEST_USER_NAME = "Test User"
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "securepass123"

# Four expenses that span two distinct date bands.
# Band A — before June 2026: one Bills expense
# Band B — June 2026 (split into early / mid): two Food, one Transport
#
# All-time totals:  total=650.00  count=4  top_category="Bills" (300 > 200 > 150)
# 2026-06-01 to 2026-06-10:  total=150.00  count=2  top_category="Food"
# 2026-06-01 to 2026-06-15:  total=350.00  count=3  top_category="Transport"
# 2099-01-01 to 2099-12-31 (empty future):  total=0  count=0  top_category="—"
#
# Breakdown for 2026-06-01 to 2026-06-15:
#   Transport 200/350 ≈ 57%,  Food 150/350 ≈ 43%  → sum = 100
# Breakdown for all time:
#   Bills 300/650 ≈ 46,  Transport 200/650 ≈ 31,  Food 150/650 ≈ 23  → sum = 100
TEST_EXPENSES = [
    (300.00, "Bills",      "2026-01-01", "Old electricity bill"),
    (100.00, "Food",       "2026-06-01", "June groceries"),
    (50.00,  "Food",       "2026-06-10", "June snacks"),
    (200.00, "Transport",  "2026-06-15", "June taxi"),
]


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """
    Create an isolated SQLite database for a single test.

    Steps:
    1. Point database.db.DB_PATH at a fresh temp file.
    2. Call init_db() to create the schema in that file.
    3. Insert one test user and four controlled expenses.
    4. Yield a dict with user credentials and known aggregate values.
    """
    db_file = tmp_path / "test_spendly.db"
    # Redirect every get_db() call made during this test to the temp file.
    monkeypatch.setattr(database.db, "DB_PATH", str(db_file))

    # Build schema in the temp file.
    init_db()

    # Seed deterministic test data.
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (
            TEST_USER_NAME,
            TEST_USER_EMAIL,
            generate_password_hash(TEST_USER_PASSWORD, method="pbkdf2:sha256"),
        ),
    )
    user_id = cursor.lastrowid

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [(user_id, amt, cat, dt, desc) for amt, cat, dt, desc in TEST_EXPENSES],
    )
    conn.commit()
    conn.close()

    yield {
        "user_id": user_id,
        "name": TEST_USER_NAME,
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD,
        # Pre-computed expected values — update here if TEST_EXPENSES changes.
        "all_time_total": 650.00,
        "all_time_count": 4,
        "all_time_top_category": "Bills",
        "june_01_10_total": 150.00,
        "june_01_10_count": 2,
        "june_01_10_top_category": "Food",
        "june_01_15_total": 350.00,
        "june_01_15_count": 3,
        "june_01_15_top_category": "Transport",
    }


@pytest.fixture
def client(tmp_db):
    """Unauthenticated Flask test client backed by the isolated temp DB."""
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
    })
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client, tmp_db):
    """Flask test client that is already logged in as the test user."""
    resp = client.post(
        "/login",
        data={"email": tmp_db["email"], "password": tmp_db["password"]},
        follow_redirects=False,
    )
    # A successful login redirects to /profile.
    assert resp.status_code == 302, (
        f"Login fixture failed — expected 302, got {resp.status_code}"
    )
    return client
