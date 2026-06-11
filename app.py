from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import database as db
from llm_service import extract_expense, predict_expense
from config import USERNAME, PASSWORD, SECRET_KEY, CATEGORY_COLORS, TIMEZONE

app = Flask(__name__)
app.secret_key = SECRET_KEY

db.init_db()


# ── Auth decorators (JSON) ─────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


def superuser_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        if session.get("role") != "superuser":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated_function


# ── API: Auth ──────────────────────────────────────────────

@app.route("/api/me")
def api_me():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "id": session["user_id"],
        "username": session.get("username"),
        "role": session.get("role"),
    })


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    user = db.get_user_by_username(username)
    if user and check_password_hash(user["password_hash"], password):
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return jsonify({"id": user["id"], "username": user["username"], "role": user["role"]})
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    confirm = data.get("confirm", "").strip()

    if not username or not password:
        return jsonify({"error": "All fields required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    if password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400
    if db.get_user_by_username(username):
        return jsonify({"error": "Username already taken"}), 400

    pw_hash = generate_password_hash(password)
    user_id = db.create_user(username, pw_hash)
    if user_id is None:
        return jsonify({"error": "Registration failed"}), 400

    session["user_id"] = user_id
    session["username"] = username
    user = db.get_user_by_id(user_id)
    session["role"] = user["role"]
    return jsonify({"id": user_id, "username": username, "role": user["role"]})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/forgot-password", methods=["POST"])
def api_forgot_password():
    data = request.get_json()
    username = data.get("username", "").strip()
    user = db.get_user_by_username(username)
    if not user:
        return jsonify({"error": "Username not found"}), 404
    token = db.create_reset_token(user["id"])
    return jsonify({"token": token})


@app.route("/api/reset/<token>")
def api_validate_reset_token(token):
    record = db.validate_reset_token(token)
    if not record:
        return jsonify({"error": "Invalid or expired reset link"}), 400
    return jsonify({"valid": True})


@app.route("/api/reset-password/<token>", methods=["POST"])
def api_reset_password(token):
    data = request.get_json()
    password = data.get("password", "").strip()
    confirm = data.get("confirm", "").strip()
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    if password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400
    pw_hash = generate_password_hash(password)
    if db.use_reset_token(token, pw_hash):
        return jsonify({"success": True})
    return jsonify({"error": "Reset failed"}), 400


# ── API: Profile ───────────────────────────────────────────

@app.route("/api/profile")
@login_required
def api_profile():
    stats = db.get_user_expense_stats(session["user_id"])
    if stats is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify(stats)


@app.route("/api/profile/change-password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json()
    user = db.get_user_by_id(session["user_id"])
    if user is None:
        return jsonify({"error": "User not found"}), 404

    current = data.get("current_password", "").strip()
    new_pass = data.get("new_password", "").strip()
    confirm = data.get("confirm_password", "").strip()

    if not check_password_hash(user["password_hash"], current):
        return jsonify({"error": "Current password is incorrect"}), 400
    if len(new_pass) < 4:
        return jsonify({"error": "New password must be at least 4 characters"}), 400
    if new_pass != confirm:
        return jsonify({"error": "Passwords do not match"}), 400

    pw_hash = generate_password_hash(new_pass)
    engine = db.get_engine()
    with engine.connect() as conn:
        conn.execute(
            db.text("UPDATE users SET password_hash = :p WHERE id = :id"),
            {"p": pw_hash, "id": session["user_id"]},
        )
        conn.commit()
    return jsonify({"success": True})


# ── API: Index (home page data) ────────────────────────────

@app.route("/api/index")
@login_required
def api_index():
    uid = session["user_id"]
    is_super = session.get("role") == "superuser"
    page = request.args.get("page", 1, type=int)
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    today_expenses = db.get_expenses_by_date(today, user_id=uid)
    today_total = sum(e["amount"] for e in today_expenses)
    month_total = db.get_month_total(user_id=uid)
    paginated = db.get_recent_expenses_paginated(
        page=page, per_page=20, user_id=None if is_super else uid
    )
    for exp in today_expenses:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    for exp in paginated["expenses"]:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    return jsonify({
        "today": today,
        "today_total": today_total,
        "month_total": month_total,
        "today_expenses": today_expenses,
        "recent_expenses": paginated["expenses"],
        "recent_page": paginated["page"],
        "recent_total_pages": paginated["total_pages"],
        "recent_total": paginated["total"],
        "category_colors": CATEGORY_COLORS,
    })


# ── API: Dashboard ─────────────────────────────────────────

@app.route("/api/dashboard")
@login_required
def api_dashboard():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    filter_user_id = request.args.get("user_id", type=int)

    is_super = session.get("role") == "superuser"
    if is_super:
        effective_user_id = filter_user_id
    else:
        effective_user_id = uid
        filter_user_id = uid

    category_totals = db.get_category_totals_by_month(year, month, user_id=effective_user_id)
    monthly_totals = db.get_monthly_totals(months=12, user_id=effective_user_id)

    paginated = db.get_expenses_filtered(
        year=year, month=month,
        user_id=effective_user_id,
        search=search if search else None,
        page=page, per_page=20,
    )

    month_total = sum(t["total"] for t in category_totals)
    db_years = db.get_distinct_years(user_id=effective_user_id if not is_super else None)
    years = sorted(set(db_years + [now.year, now.year + 1, now.year + 2, now.year + 3]))
    users_list = db.get_all_users() if is_super else []

    for exp in paginated["expenses"]:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")

    return jsonify({
        "category_totals": category_totals,
        "monthly_totals": monthly_totals,
        "month_total": month_total,
        "year": year,
        "month": month,
        "years": years,
        "page": paginated["page"],
        "per_page": paginated["per_page"],
        "total": paginated["total"],
        "total_pages": paginated["total_pages"],
        "month_expenses": paginated["expenses"],
        "search_query": search,
        "filter_user_id": filter_user_id,
        "users_list": users_list,
        "category_colors": CATEGORY_COLORS,
        "role": session.get("role"),
    })


# ── API: Admin ─────────────────────────────────────────────

@app.route("/api/admin/users")
@login_required
@superuser_required
def api_admin_users():
    users = db.get_all_users()
    for u in users:
        u.pop("password_hash", None)
    return jsonify({"users": users})


@app.route("/api/admin/users/<int:user_id>/change-role", methods=["POST"])
@login_required
@superuser_required
def api_admin_change_role(user_id):
    if user_id == session["user_id"]:
        return jsonify({"error": "Cannot change own role"}), 400
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    new_role = "user" if user["role"] == "superuser" else "superuser"
    db.update_user_role(user_id, new_role)
    return jsonify({"success": True, "new_role": new_role})


@app.route("/api/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@superuser_required
def api_admin_delete_user(user_id):
    if user_id == session["user_id"]:
        return jsonify({"error": "Cannot delete yourself"}), 400
    db.delete_user(user_id)
    return jsonify({"success": True})


# ── Existing API routes (unchanged) ────────────────────────

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
        year=year, month=month,
        user_id=effective_user_id,
        search=search if search else None,
    )

    filename = f"expenses_{year}_{month:02d}"

    if fmt == "csv":
        from export_service import generate_csv
        data = generate_csv(expenses, year, month)
        return (
            data, 200,
            {
                "Content-Type": "text/csv",
                "Content-Disposition": f'attachment; filename="{filename}.csv"',
            },
        )
    elif fmt == "xlsx":
        from export_service import generate_xlsx
        buf = generate_xlsx(expenses, year, month)
        return (
            buf.read(), 200,
            {
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Content-Disposition": f'attachment; filename="{filename}.xlsx"',
            },
        )
    elif fmt == "pdf":
        from export_service import generate_pdf
        buf = generate_pdf(expenses, year, month)
        return (
            buf.read(), 200,
            {
                "Content-Type": "application/pdf",
                "Content-Disposition": f'attachment; filename="{filename}.pdf"',
            },
        )
    else:
        return jsonify({"error": "Unsupported format. Use csv, xlsx, or pdf."}), 400


# ── SPA catch-all ─────────────────────────────────────────

@app.route("/")
@app.route("/<path:path>")
def spa_shell(path=None):
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
