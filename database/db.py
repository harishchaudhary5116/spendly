import os
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "spendly.db",
)

CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    conn = get_db()
    try:
        existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if existing > 0:
            return

        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (
                "Demo User",
                "demo@spendly.com",
                generate_password_hash("demo123", method="pbkdf2:sha256"),
            ),
        )
        user_id = cursor.lastrowid

        sample_expenses = [
            (user_id, 250.00, "Food", "2026-06-02", "Groceries"),
            (user_id, 180.50, "Food", "2026-06-18", "Dinner with friends"),
            (user_id, 90.00, "Transport", "2026-06-05", "Metro card top-up"),
            (user_id, 1200.00, "Bills", "2026-06-08", "Electricity bill"),
            (user_id, 450.00, "Health", "2026-06-11", "Pharmacy"),
            (user_id, 350.00, "Entertainment", "2026-06-14", "Movie tickets"),
            (user_id, 1499.00, "Shopping", "2026-06-20", "New shoes"),
            (user_id, 200.00, "Other", "2026-06-23", "Misc"),
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            sample_expenses,
        )
        conn.commit()
    finally:
        conn.close()


def create_user(name, email, password):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password, method="pbkdf2:sha256")),
        )
        conn.commit()
    finally:
        conn.close()


def authenticate_user(email, password):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return row
