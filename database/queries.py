"""Query helpers for the profile dashboard.

Each helper opens a connection via get_db(), runs a single read,
closes the connection in a finally block, and returns plain Python
values (dict, list, or None). No Flask imports here.
"""

from datetime import datetime

from database.db import get_db


def _date_where(user_id, start_date, end_date):
    clause = "WHERE user_id = ?"
    params = [user_id]
    if start_date:
        clause += " AND date >= ?"
        params.append(start_date)
    if end_date:
        clause += " AND date <= ?"
        params.append(end_date)
    return clause, params


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    member_since = ""
    if row["created_at"]:
        try:
            dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            member_since = dt.strftime("%B %Y")
        except ValueError:
            member_since = ""

    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": member_since,
    }


def get_summary_stats(user_id, *, start_date=None, end_date=None):
    where, params = _date_where(user_id, start_date, end_date)

    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total_spent, "
            "COUNT(*) AS transaction_count "
            "FROM expenses " + where,
            params,
        ).fetchone()

        top = conn.execute(
            "SELECT category FROM expenses " + where + " "
            "GROUP BY category "
            "ORDER BY SUM(amount) DESC, category ASC "
            "LIMIT 1",
            params,
        ).fetchone()
    finally:
        conn.close()

    transaction_count = totals["transaction_count"] if totals else 0
    if not transaction_count:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    return {
        "total_spent": float(totals["total_spent"]),
        "transaction_count": int(transaction_count),
        "top_category": top["category"] if top else "—",
    }


def get_recent_transactions(user_id, limit=10, *, start_date=None, end_date=None):
    where, params = _date_where(user_id, start_date, end_date)
    params.append(limit)

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount "
            "FROM expenses " + where + " "
            "ORDER BY date DESC, id DESC "
            "LIMIT ?",
            params,
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in rows
    ]


def get_category_breakdown(user_id, *, start_date=None, end_date=None):
    where, params = _date_where(user_id, start_date, end_date)

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total "
            "FROM expenses " + where + " "
            "GROUP BY category "
            "ORDER BY total DESC",
            params,
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)
    if grand_total <= 0:
        return []

    breakdown = [
        {
            "name": row["category"],
            "amount": float(row["total"]),
            "pct": int(round(row["total"] / grand_total * 100)),
        }
        for row in rows
    ]

    diff = 100 - sum(item["pct"] for item in breakdown)
    if diff != 0:
        breakdown[0]["pct"] += diff

    return breakdown
