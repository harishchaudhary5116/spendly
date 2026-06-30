import os
import re
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, redirect, render_template, request, session, url_for

from database.db import (
    authenticate_user,
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
    last_30_start = (today - timedelta(days=29)).isoformat()
    today_iso = today.isoformat()

    preset_urls = {
        "this_month": url_for(
            "profile", start_date=this_month_start, end_date=today_iso
        ),
        "last_30": url_for(
            "profile", start_date=last_30_start, end_date=today_iso
        ),
        "all_time": url_for("profile"),
    }

    if start_str is None and end_str is None:
        active_preset = "all_time"
    elif (start_str, end_str) == (this_month_start, today_iso):
        active_preset = "this_month"
    elif (start_str, end_str) == (last_30_start, today_iso):
        active_preset = "last_30"
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


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
