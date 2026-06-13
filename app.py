from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import re
import database as db
from llm_service import extract_expense, predict_expense, extract_keywords, generate_sql, answer_from_results, format_answer, split_expenses, _clean_split_desc, extract_date_reference, clean_date_refs, detect_budget_intent, is_question, transcribe_audio
from config import USERNAME, PASSWORD, SECRET_KEY, CATEGORY_COLORS, TIMEZONE, SEED_CATEGORIES

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ── Close DB connection after each request ─────────────────
@app.teardown_appcontext
def shutdown_db_connection(exception=None):
    db.close_connection()


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


# ── SQL safety validation ─────────────────────────────────

def _validate_sql(sql):
    s = sql.strip()
    while s.endswith(";"):
        s = s[:-1].strip()
    if not s.upper().startswith("SELECT"):
        return False
    if "--" in s or "/*" in s or "*/" in s:
        return False
    forbidden = {"DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE", "REPLACE", "EXEC"}
    words = re.findall(r'\b\w+\b', s.upper())
    for word in words:
        if word in forbidden:
            return False
    return True


def _ensure_user_filter(sql):
    if ":uid" in sql:
        return sql
    clauses = ["ORDER BY", "GROUP BY", "LIMIT", "HAVING"]
    sql_upper = sql.upper()
    insert_pos = len(sql)
    for clause in clauses:
        pos = sql_upper.find(clause)
        if pos != -1 and pos < insert_pos:
            insert_pos = pos
    prefix = sql[:insert_pos].upper()
    if "WHERE" in prefix:
        return sql[:insert_pos] + " AND user_id = :uid " + sql[insert_pos:]
    return sql[:insert_pos] + " WHERE user_id = :uid " + sql[insert_pos:]


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
    conn = db.get_connection()
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
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=15)).strftime("%Y-%m-%d")
    paginated = db.get_recent_expenses_paginated(
        page=page, per_page=20, user_id=None if is_super else uid, since=cutoff
    )
    for exp in today_expenses:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    for exp in paginated["expenses"]:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    budget_status = db.get_budget_status(uid)
    budget_alerts = [b for b in budget_status if b["percentage"] >= 80]
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
        "budget_alerts": budget_alerts,
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


# ── API: Learn ──────────────────────────────────────────────

@app.route("/api/learn", methods=["POST"])
@login_required
def api_learn():
    data = request.get_json()
    description = data.get("description", "").strip()
    category = data.get("category", "").strip()
    if not description or not category:
        return jsonify({"error": "description and category required"}), 400
    for kw in extract_keywords(description):
        db.learn_category(session["user_id"], kw, category)
    return jsonify({"success": True})


# ── NL Q&A schema cache ──────────────────────────────────
_schema_cache = None
_schema_cache_time = 0
import time as _time

def _get_schema_cached():
    global _schema_cache, _schema_cache_time
    now = _time.time()
    if _schema_cache and now - _schema_cache_time < 300:
        return _schema_cache
    _schema_cache = db.get_schema()
    _schema_cache_time = now
    return _schema_cache

COMPLEX_KEYWORDS = [
    "compare", "comparison", "difference", "vs ", "versus",
    "trend", "pattern",
    "unusual", "abnormal", "unexpected", "strange",
    "why", "because", "reason",
    "recommend", "suggestion", "tip", "advice",
    "insight", "summarize", "summary", "overview",
    "improve", "save", "reduce", "cut",
    "increased", "decreased", "rose", "fell",
]

def _needs_llm_answer(question):
    q = question.lower()
    return any(kw in q for kw in COMPLEX_KEYWORDS)


# ── NL Q&A ──────────────────────────────────────────────────

@app.route("/api/ask", methods=["POST"])
@login_required
def api_ask():
    data = request.get_json()
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question required"}), 400

    history = data.get("history", [])

    schema = _get_schema_cached()
    current_date = datetime.now(TIMEZONE).strftime("%B %d, %Y")
    question_with_context = f"Today is {current_date}.\n\nQuestion: {question}"

    try:
        sql = generate_sql(question_with_context, schema)
    except Exception as e:
        return jsonify({"error": f"LLM query failed: {str(e)}"}), 500
    if not sql:
        return jsonify({"error": "Could not generate SQL query. Check API key."}), 500

    if not _validate_sql(sql):
        return jsonify({"error": "Generated query is not a valid SELECT statement"}), 500

    sql = _ensure_user_filter(sql)

    try:
        conn = db.get_connection()
        result = conn.execute(db.text(sql), {"uid": session["user_id"]})
        columns = list(result.keys()) if result.returns_rows else []
        rows = result.fetchmany(50)
        rows_data = [dict(r._mapping) for r in rows]
    except Exception as e:
        return jsonify({"error": f"Query execution failed: {str(e)}", "sql": sql}), 500

    # Use programmatic answer for simple queries, LLM only for complex ones
    if _needs_llm_answer(question):
        answer = answer_from_results(question, sql, rows_data[:20], history=history)
        if not answer:
            answer = format_answer(columns, rows_data, question)
    else:
        answer = format_answer(columns, rows_data, question)

    return jsonify({
        "answer": answer,
        "sql": sql,
        "data": rows_data[:50],
        "columns": columns,
    })


# ── Chat (unified expense + Q&A) ──────────────────────────

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if len(message) < 2:
        return jsonify({"error": "Message required"}), 400

    learned = db.get_learned_categories(session["user_id"])

    skip_expense = is_question(message)

    # Extract date reference, then use cleaned text for expense parsing
    cleaned_message, expense_date = extract_date_reference(message, datetime.now(TIMEZONE))

    # Step 0: Check for budget intent BEFORE expense parsing
    budget_intent = detect_budget_intent(message)
    if budget_intent:
        return jsonify({"type": "budget", "category": budget_intent["category"], "amount": budget_intent["amount"]})

    if not skip_expense:
        # Step 1: Try expense parsing via split_expenses (handles multi & single item)
        items = split_expenses(cleaned_message)
        if items and all(item.get("amount", 0) > 0 for item in items):
            for item in items:
                item["description"] = clean_date_refs(item.get("description", ""))
                item["color"] = CATEGORY_COLORS.get(item["category"], "#6b7280")
            return jsonify({"type": "expense", "date": expense_date, "items": items})

        # Step 2: Try single-item prediction
        prediction = predict_expense(cleaned_message, learned_categories=learned)
        if prediction and prediction.get("amount", 0) > 0:
            cat = prediction["category"]
            return jsonify({
                "type": "expense",
                "date": expense_date,
                "items": [{
                    "description": clean_date_refs(_clean_split_desc(cleaned_message) or cleaned_message),
                    "category": cat,
                    "amount": prediction["amount"],
                    "color": CATEGORY_COLORS.get(cat, "#6b7280"),
                }]
            })

    # Step 3: Fall through to Q&A
    schema = _get_schema_cached()
    current_date = datetime.now(TIMEZONE).strftime("%B %d, %Y")
    question_with_context = f"Today is {current_date}.\n\nQuestion: {message}"

    try:
        sql = generate_sql(question_with_context, schema)
    except Exception as e:
        return jsonify({"error": f"LLM query failed: {str(e)}"}), 500
    if not sql:
        return jsonify({"error": "Could not generate SQL query. Check API key."}), 500

    if not _validate_sql(sql):
        return jsonify({"error": "Generated query is not a valid SELECT statement"}), 500

    sql = _ensure_user_filter(sql)

    try:
        conn = db.get_connection()
        result = conn.execute(db.text(sql), {"uid": session["user_id"]})
        columns = list(result.keys()) if result.returns_rows else []
        rows = result.fetchmany(50)
        rows_data = [dict(r._mapping) for r in rows]
    except Exception as e:
        return jsonify({"error": f"Query execution failed: {str(e)}", "sql": sql}), 500

    if _needs_llm_answer(message):
        answer = answer_from_results(message, sql, rows_data[:20], history=history)
        if not answer:
            answer = format_answer(columns, rows_data, message)
    else:
        answer = format_answer(columns, rows_data, message)

    return jsonify({
        "type": "question",
        "answer": answer,
        "sql": sql,
        "data": rows_data[:50],
        "columns": columns,
    })


# ── Expense Splitting ──────────────────────────────────────

@app.route("/api/split_expense", methods=["POST"])
@login_required
def api_split_expense():
    data = request.get_json()
    description = data.get("description", "").strip()
    if len(description) < 2:
        return jsonify({"error": "Description required"}), 400

    items = split_expenses(description)
    if not items or len(items) < 2:
        return jsonify({"items": None, "message": "Could not split into multiple items"})

    learned = db.get_learned_categories(session["user_id"])
    for item in items:
        item["color"] = CATEGORY_COLORS.get(item["category"], "#6b7280")
    return jsonify({"items": items})


@app.route("/api/expenses/bulk", methods=["POST"])
@login_required
def api_expenses_bulk():
    data = request.get_json()
    date = data.get("date", datetime.now(TIMEZONE).strftime("%Y-%m-%d"))
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "No items provided"}), 400

    saved = []
    for item in items:
        desc = clean_date_refs(item.get("description", "")).strip()
        category = item.get("category", "").strip()
        amount = float(item.get("amount", 0))
        if not desc or amount <= 0:
            continue

        # Auto-learn from confirmed split items
        for kw in extract_keywords(desc):
            db.learn_category(session["user_id"], kw, category)

        expense_id = db.add_expense(date, desc, amount, category, user_id=session["user_id"])
        saved.append({
            "id": expense_id,
            "date": date,
            "description": desc,
            "amount": amount,
            "category": category,
            "color": CATEGORY_COLORS.get(category, "#6b7280"),
        })

    budget_alerts = db.get_budget_status(session["user_id"])
    budget_alerts = [b for b in budget_alerts if b["percentage"] >= 80]
    return jsonify({"count": len(saved), "expenses": saved, "budget_alerts": budget_alerts})


# ── Existing API routes (unchanged) ────────────────────────

@app.route("/api/add_expense", methods=["POST"])
@login_required
def api_add_expense():
    data = request.get_json()
    date = data.get("date", datetime.now(TIMEZONE).strftime("%Y-%m-%d"))
    description = data.get("description", "").strip()

    if not description:
        return jsonify({"error": "Description required"}), 400

    # Clean description: strip trailing monetary amounts, keep quantity modifiers (1 kg, 2 ta, etc.)
    clean_desc = _clean_split_desc(description) or description

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

    # Learn from user-corrected predictions
    if data.get("learn"):
        for kw in extract_keywords(clean_desc):
            db.learn_category(session["user_id"], kw, category)

    expense_id = db.add_expense(date, clean_desc, amount, category, user_id=session["user_id"])

    budget_alerts = db.get_budget_status(session["user_id"])
    budget_alerts = [b for b in budget_alerts if b["percentage"] >= 80]

    return jsonify(
        {
            "id": expense_id,
            "date": date,
            "description": clean_desc,
            "amount": amount,
            "category": category,
            "color": CATEGORY_COLORS.get(category, "#6b7280"),
            "budget_alerts": budget_alerts,
        }
    )


@app.route("/api/predict_expense", methods=["POST"])
@login_required
def api_predict_expense():
    data = request.get_json()
    description = data.get("description", "").strip()

    if len(description) < 2:
        return jsonify({"category": None, "amount": None})

    learned = db.get_learned_categories(session["user_id"])
    result = predict_expense(description, learned_categories=learned)
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


@app.route("/api/expenses/category-breakdown")
@login_required
def api_category_breakdown():
    uid = session["user_id"]
    is_super = session.get("role") == "superuser"
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    category = request.args.get("category", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    if not year or not month or not category:
        return jsonify({"error": "year, month, and category required"}), 400
    filter_user_id = request.args.get("user_id", type=int)
    effective_user_id = filter_user_id if is_super else uid
    data = db.get_expenses_by_category_month(year, month, category, user_id=effective_user_id, page=page, per_page=per_page)
    for exp in data["expenses"]:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    return jsonify(data)


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


# ── API: Categories ────────────────────────────────────────────

@app.route("/api/categories", methods=["GET"])
@login_required
def api_categories():
    return jsonify({"categories": list(CATEGORY_COLORS.keys()), "colors": CATEGORY_COLORS})


# ── API: Budgets ──────────────────────────────────────────────

@app.route("/api/budgets", methods=["GET"])
@login_required
def api_get_budgets():
    uid = session["user_id"]
    budgets = db.get_budgets(uid)
    budget_status = db.get_budget_status(uid)
    status_map = {b["category"]: b for b in budget_status}
    for b in budgets:
        s = status_map.get(b["category"], {})
        b["spent"] = s.get("spent", 0)
        b["percentage"] = s.get("percentage", 0)
        b["color"] = CATEGORY_COLORS.get(b["category"], "#6b7280")
    return jsonify({"budgets": budgets})


@app.route("/api/budgets/set", methods=["POST"])
@login_required
def api_set_budget():
    data = request.get_json()
    uid = session["user_id"]
    category = data.get("category", "").strip()
    amount = data.get("amount", 0)
    if not category:
        return jsonify({"error": "Category is required"}), 400
    if not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({"error": "Amount must be a positive number"}), 400
    db.set_budget(uid, category, amount)
    return jsonify({"success": True, "category": category, "amount": amount})


@app.route("/api/budgets/delete/<int:budget_id>", methods=["DELETE"])
@login_required
def api_delete_budget(budget_id):
    db.delete_budget(budget_id)
    return jsonify({"success": True})


@app.route("/api/budgets/status", methods=["GET"])
@login_required
def api_budget_status():
    uid = session["user_id"]
    month = request.args.get("month")
    status = db.get_budget_status(uid, month=month)
    return jsonify({"budget_status": status})


# ── Audio transcription ────────────────────────────────────

@app.route("/api/transcribe", methods=["POST"])
@login_required
def api_transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    audio = request.files["audio"]
    mime_type = audio.content_type or "audio/webm"
    try:
        text = transcribe_audio(audio.read(), mime_type)
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── SPA catch-all ─────────────────────────────────────────

@app.route("/")
@app.route("/<path:path>")
def spa_shell(path=None):
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
