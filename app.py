import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for

from database.db import (
    authenticate_user,
    create_user,
    get_user_by_id,
    init_db,
    seed_db,
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


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    member_since = None
    if user["created_at"]:
        try:
            dt = datetime.strptime(user["created_at"], "%Y-%m-%d %H:%M:%S")
            member_since = dt.strftime("%B %Y")
        except ValueError:
            member_since = None

    return render_template("profile.html", user=user, member_since=member_since)


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
