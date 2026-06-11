from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import math
import database as db
from llm_service import extract_expense, predict_expense
from config import USERNAME, PASSWORD, SECRET_KEY, CATEGORY_COLORS, TIMEZONE

app = Flask(__name__)
app.secret_key = SECRET_KEY

db.init_db()


# ── Auth decorators ─────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def superuser_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "superuser":
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function


# ── Auth routes ─────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = db.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm", "").strip()

        if not username or not password:
            return render_template("register.html", error="All fields required")
        if len(username) < 3:
            return render_template("register.html", error="Username must be at least 3 characters")
        if len(password) < 4:
            return render_template("register.html", error="Password must be at least 4 characters")
        if password != confirm:
            return render_template("register.html", error="Passwords do not match")
        if db.get_user_by_username(username):
            return render_template("register.html", error="Username already taken")

        pw_hash = generate_password_hash(password)
        user_id = db.create_user(username, pw_hash)
        if user_id is None:
            return render_template("register.html", error="Registration failed")

        session["user_id"] = user_id
        session["username"] = username
        user = db.get_user_by_id(user_id)
        session["role"] = user["role"]
        return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("role", None)
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = db.get_user_by_username(username)
        if not user:
            return render_template("forgot_password.html", error="Username not found")
        token = db.create_reset_token(user["id"])
        return redirect(url_for("reset_password", token=token))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    record = db.validate_reset_token(token)
    if not record:
        return render_template("reset_password.html", error="Invalid or expired reset link", valid=False)

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm", "").strip()
        if len(password) < 4:
            return render_template("reset_password.html", error="Password must be at least 4 characters", valid=True)
        if password != confirm:
            return render_template("reset_password.html", error="Passwords do not match", valid=True)
        pw_hash = generate_password_hash(password)
        if db.use_reset_token(token, pw_hash):
            return redirect(url_for("login"))
        return render_template("reset_password.html", error="Reset failed. Try again.", valid=True)
    return render_template("reset_password.html", valid=True)


# ── Profile routes ──────────────────────────────────────────

@app.route("/profile", methods=["GET"])
@login_required
def profile():
    stats = db.get_user_expense_stats(session["user_id"])
    if stats is None:
        session.clear()
        return redirect(url_for("login"))
    return render_template("profile.html", stats=stats)


@app.route("/profile/change-password", methods=["POST"])
@login_required
def change_password():
    user = db.get_user_by_id(session["user_id"])
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    current = request.form.get("current_password", "").strip()
    new_pass = request.form.get("new_password", "").strip()
    confirm = request.form.get("confirm_password", "").strip()

    if not check_password_hash(user["password_hash"], current):
        stats = db.get_user_expense_stats(session["user_id"])
        return render_template("profile.html", stats=stats, pw_error="Current password is incorrect")
    if len(new_pass) < 4:
        stats = db.get_user_expense_stats(session["user_id"])
        return render_template("profile.html", stats=stats, pw_error="New password must be at least 4 characters")
    if new_pass != confirm:
        stats = db.get_user_expense_stats(session["user_id"])
        return render_template("profile.html", stats=stats, pw_error="Passwords do not match")

    pw_hash = generate_password_hash(new_pass)
    engine = db.get_engine()
    with engine.connect() as conn:
        conn.execute(
            db.text("UPDATE users SET password_hash = :p WHERE id = :id"),
            {"p": pw_hash, "id": session["user_id"]},
        )
        conn.commit()
    stats = db.get_user_expense_stats(session["user_id"])
    return render_template("profile.html", stats=stats, pw_success="Password updated successfully")


# ── Superuser admin routes ──────────────────────────────────

@app.route("/admin/users")
@login_required
@superuser_required
def admin_users():
    users = db.get_all_users()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/change-role", methods=["POST"])
@login_required
@superuser_required
def admin_change_role(user_id):
    if user_id == session["user_id"]:
        return redirect(url_for("admin_users"))
    user = db.get_user_by_id(user_id)
    if not user:
        return redirect(url_for("admin_users"))
    new_role = "user" if user["role"] == "superuser" else "superuser"
    db.update_user_role(user_id, new_role)
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@superuser_required
def admin_delete_user(user_id):
    if user_id != session["user_id"]:
        db.delete_user(user_id)
    return redirect(url_for("admin_users"))


# ── Main routes ─────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    uid = session["user_id"]
    is_super = session.get("role") == "superuser"
    page = request.args.get("page", 1, type=int)
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    today_expenses = db.get_expenses_by_date(today, user_id=uid)
    today_total = db.get_today_total(user_id=uid)
    month_total = db.get_month_total(user_id=uid)
    paginated = db.get_recent_expenses_paginated(
        page=page, per_page=20, user_id=None if is_super else uid
    )
    return render_template(
        "index.html",
        today_expenses=today_expenses,
        today_total=today_total,
        month_total=month_total,
        recent_expenses=paginated["expenses"],
        recent_page=paginated["page"],
        recent_total_pages=paginated["total_pages"],
        recent_total=paginated["total"],
        today=today,
        category_colors=CATEGORY_COLORS,
        role=session.get("role"),
    )


@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    filter_user_id = request.args.get("user_id", type=int)

    is_super = session.get("role") == "superuser"
    if is_super:
        effective_user_id = filter_user_id  # None = all
    else:
        effective_user_id = uid
        filter_user_id = uid

    category_totals = db.get_category_totals_by_month(year, month, user_id=effective_user_id)
    monthly_totals = db.get_monthly_totals(months=12, user_id=effective_user_id)

    paginated = db.get_expenses_filtered(
        year=year,
        month=month,
        user_id=effective_user_id,
        search=search if search else None,
        page=page,
        per_page=20,
    )

    month_total = sum(t["total"] for t in category_totals)
    db_years = db.get_distinct_years(user_id=effective_user_id if not is_super else None)
    years = sorted(set(db_years + [now.year, now.year + 1, now.year + 2, now.year + 3]))

    users_list = db.get_all_users() if is_super else []

    return render_template(
        "dashboard.html",
        category_totals=category_totals,
        monthly_totals=monthly_totals,
        month_total=month_total,
        year=year,
        month=month,
        years=years,
        page=paginated["page"],
        per_page=paginated["per_page"],
        total=paginated["total"],
        total_pages=paginated["total_pages"],
        month_expenses=paginated["expenses"],
        search_query=search,
        filter_user_id=filter_user_id,
        users_list=users_list,
        category_colors=CATEGORY_COLORS,
        role=session.get("role"),
    )


# ── Export routes ────────────────────────────────────────────

@app.route("/api/export/<fmt>")
@login_required
def api_export(fmt):
    uid = session["user_id"]
    is_super = session.get("role") == "superuser"
    now = datetime.now(TIMEZONE)
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    search = request.args.get("search", "").strip()
    filter_user_id = request.args.get("user_id", type=int)

    if is_super:
        effective_user_id = filter_user_id
    else:
        effective_user_id = uid

    expenses = db.get_expenses_export(
        year=year,
        month=month,
        user_id=effective_user_id,
        search=search if search else None,
    )

    filename = f"expenses_{year}_{month:02d}"

    if fmt == "csv":
        from export_service import generate_csv
        data = generate_csv(expenses, year, month)
        return (
            data,
            200,
            {
                "Content-Type": "text/csv",
                "Content-Disposition": f'attachment; filename="{filename}.csv"',
            },
        )
    elif fmt == "xlsx":
        from export_service import generate_xlsx
        buf = generate_xlsx(expenses, year, month)
        return (
            buf.read(),
            200,
            {
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Content-Disposition": f'attachment; filename="{filename}.xlsx"',
            },
        )
    elif fmt == "pdf":
        from export_service import generate_pdf
        buf = generate_pdf(expenses, year, month)
        return (
            buf.read(),
            200,
            {
                "Content-Type": "application/pdf",
                "Content-Disposition": f'attachment; filename="{filename}.pdf"',
            },
        )
    else:
        return jsonify({"error": "Unsupported format. Use csv, xlsx, or pdf."}), 400


# ── API routes ──────────────────────────────────────────────

@app.route("/api/add_expense", methods=["POST"])
@login_required
def api_add_expense():
    data = request.get_json()
    date = data.get("date", datetime.now(TIMEZONE).strftime("%Y-%m-%d"))
    description = data.get("description", "").strip()

    if not description:
        return jsonify({"error": "Description required"}), 400

    category = data.get("category")
    amount = data.get("amount")

    if category and amount is not None and float(amount) > 0:
        amount = float(amount)
    else:
        result = extract_expense(description)
        category = result["category"]
        amount = result["amount"]

    if amount <= 0:
        return jsonify({"error": "Could not extract amount. Please include the amount in your text."}), 400

    expense_id = db.add_expense(date, description, amount, category, user_id=session["user_id"])

    return jsonify(
        {
            "id": expense_id,
            "date": date,
            "description": description,
            "amount": amount,
            "category": category,
            "color": CATEGORY_COLORS.get(category, "#6b7280"),
        }
    )


@app.route("/api/predict_expense", methods=["POST"])
@login_required
def api_predict_expense():
    data = request.get_json()
    description = data.get("description", "").strip()

    if len(description) < 2:
        return jsonify({"category": None, "amount": None})

    result = predict_expense(description)
    if result:
        return jsonify(
            {
                "category": result["category"],
                "amount": result["amount"],
                "color": CATEGORY_COLORS.get(result["category"], "#6b7280"),
            }
        )
    return jsonify({"category": None, "amount": None})


@app.route("/api/delete_expense/<int:expense_id>", methods=["DELETE"])
@login_required
def api_delete_expense(expense_id):
    db.delete_expense(expense_id)
    return jsonify({"success": True})


@app.route("/api/expenses/<date>")
@login_required
def api_expenses_by_date(date):
    uid = session["user_id"]
    expenses = db.get_expenses_by_date(date, user_id=uid)
    for exp in expenses:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    return jsonify(expenses)


@app.route("/api/expenses/month")
@login_required
def api_expenses_by_month():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    expenses = db.get_expenses_by_month(year, month, user_id=uid)
    for exp in expenses:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    return jsonify(expenses)


@app.route("/api/expenses/monthly-totals")
@login_required
def api_monthly_totals():
    uid = session["user_id"]
    months = request.args.get("months", 6, type=int)
    return jsonify(db.get_monthly_totals(months=months, user_id=uid))


@app.route("/api/expenses/category-totals")
@login_required
def api_category_totals():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    return jsonify(db.get_category_totals_by_month(year, month, user_id=uid))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
