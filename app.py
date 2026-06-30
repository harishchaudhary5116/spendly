import hmac
import math
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, redirect, render_template, request, session, url_for

from database.db import (
    CATEGORIES,
    authenticate_user,
    create_expense,
    create_user,
    init_db,
    seed_db,
)
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__)
# Override via env var in production.
app.secret_key = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-change-in-production")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not name or not email or not password:
        return render_template(
            "register.html",
            error="Please fill in every field.",
            name=name,
            email=email,
        )
    if not (2 <= len(name) <= 80):
        return render_template(
            "register.html",
            error="Name must be between 2 and 80 characters.",
            name=name,
            email=email,
        )
    if len(email) > 120 or not EMAIL_RE.match(email):
        return render_template(
            "register.html",
            error="Please enter a valid email address.",
            name=name,
            email=email,
        )
    if len(password) < 8:
        return render_template(
            "register.html",
            error="Password must be at least 8 characters.",
            name=name,
            email=email,
        )

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        return render_template(
            "register.html",
            error="That email is already registered.",
            name=name,
            email=email,
        )

    return redirect(url_for("login") + "?registered=1")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        success = (
            "Account created — please sign in."
            if request.args.get("registered") == "1"
            else None
        )
        return render_template("login.html", success=success)

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template(
            "login.html",
            error="Invalid email or password.",
            email=email,
        )

    user = authenticate_user(email, password)
    if user is None:
        return render_template(
            "login.html",
            error="Invalid email or password.",
            email=email,
        )

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


def _get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _csrf_valid(submitted):
    expected = session.get("csrf_token")
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _fmt_day(d):
    return f"{d.day} {d.strftime('%b %Y')}"


def _build_filter_context(raw_start, raw_end):
    start = _parse_date(raw_start)
    end = _parse_date(raw_end)

    if (raw_start and start is None) or (raw_end and end is None):
        start = end = None
    elif start and end and start > end:
        start = end = None

    start_str = start.isoformat() if start else None
    end_str = end.isoformat() if end else None

    today = date.today()
    this_month_start = today.replace(day=1).isoformat()
    last_3_start = (today - timedelta(days=90)).isoformat()
    last_6_start = (today - timedelta(days=180)).isoformat()
    today_iso = today.isoformat()

    preset_urls = {
        "all_time": url_for("profile"),
        "this_month": url_for(
            "profile", start_date=this_month_start, end_date=today_iso
        ),
        "last_3_months": url_for(
            "profile", start_date=last_3_start, end_date=today_iso
        ),
        "last_6_months": url_for(
            "profile", start_date=last_6_start, end_date=today_iso
        ),
    }

    if (start_str, end_str) == (this_month_start, today_iso):
        active_preset = "this_month"
    elif (start_str, end_str) == (last_3_start, today_iso):
        active_preset = "last_3_months"
    elif (start_str, end_str) == (last_6_start, today_iso):
        active_preset = "last_6_months"
    elif start_str is None and end_str is None:
        active_preset = "all_time"
    else:
        active_preset = None

    filter_caption = None
    if start and end:
        filter_caption = f"{_fmt_day(start)} → {_fmt_day(end)}"
    elif start:
        filter_caption = f"from {_fmt_day(start)}"
    elif end:
        filter_caption = f"up to {_fmt_day(end)}"

    return {
        "start_str": start_str,
        "end_str": end_str,
        "start_value": start_str or "",
        "end_value": end_str or "",
        "preset_urls": preset_urls,
        "active_preset": active_preset,
        "filter_caption": filter_caption,
    }


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    ctx = _build_filter_context(
        request.args.get("start_date", "").strip()[:10],
        request.args.get("end_date", "").strip()[:10],
    )

    return render_template(
        "profile.html",
        user=user,
        stats=get_summary_stats(
            user_id, start_date=ctx["start_str"], end_date=ctx["end_str"]
        ),
        transactions=get_recent_transactions(
            user_id, start_date=ctx["start_str"], end_date=ctx["end_str"]
        ),
        breakdown=get_category_breakdown(
            user_id, start_date=ctx["start_str"], end_date=ctx["end_str"]
        ),
        start_value=ctx["start_value"],
        end_value=ctx["end_value"],
        preset_urls=ctx["preset_urls"],
        active_preset=ctx["active_preset"],
        filter_caption=ctx["filter_caption"],
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    today_iso = date.today().isoformat()
    csrf_token = _get_csrf_token()

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            amount="",
            category="Food",
            expense_date=today_iso,
            description="",
            csrf_token=csrf_token,
        )

    if not _csrf_valid(request.form.get("csrf_token")):
        return redirect(url_for("add_expense"))

    raw_amount = request.form.get("amount", "").strip()
    raw_category = request.form.get("category", "").strip()
    raw_date = request.form.get("date", "").strip()
    raw_description = request.form.get("description", "").strip()

    def _render_error(msg):
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            error=msg,
            amount=raw_amount,
            category=raw_category or "Food",
            expense_date=raw_date or today_iso,
            description=raw_description,
            csrf_token=csrf_token,
        )

    try:
        amount_val = float(raw_amount)
    except ValueError:
        return _render_error("Please enter a valid amount.")
    if not math.isfinite(amount_val):
        return _render_error("Please enter a valid amount.")
    if amount_val <= 0 or amount_val > 9_999_999.99:
        return _render_error(
            "Amount must be greater than 0 and at most ₹9,999,999.99."
        )

    if raw_category not in CATEGORIES:
        return _render_error("Please choose a valid category.")

    parsed_date = _parse_date(raw_date)
    if parsed_date is None or parsed_date > date.today():
        return _render_error(
            "Please enter a valid date that is not in the future."
        )

    description_val = raw_description[:200] if raw_description else None

    create_expense(
        user_id,
        amount_val,
        raw_category,
        parsed_date.isoformat(),
        description_val,
    )
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
