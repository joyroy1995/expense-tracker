import os
from flask import Flask, render_template, request, session, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash
import re
import random
import calendar
import json
import database as db
from database import _ALL_CATEGORIES
from llm import extract_expense, predict_expense, extract_keywords, split_expenses, _clean_split_desc, extract_date_reference, clean_date_refs, detect_budget_intent, is_question, transcribe_audio, scan_receipt, generate_forecast, extract_session_reason
from llm.categories import GROCERY_SUBCATEGORIES, grocery_subcategory
from config import SECRET_KEY, CATEGORY_COLORS, TIMEZONE
from services.sql_service import SqlService
from services.qa_service import QaService
from services.notification_service import NotificationService

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_HTTPONLY=True,
)

def _rate_limit_key():
    return str(session.get("user_id", get_remote_address()))

limiter = Limiter(
    app=app,
    key_func=_rate_limit_key,
    default_limits=["120 per minute"],
    storage_uri="memory://",
    enabled=os.environ.get("RATELIMIT_ENABLED", "1") != "0",
)

def _static_version():
    v = 1
    for name in ('style.css', 'script.js'):
        fp = os.path.join(app.static_folder, name)
        try:
            m = int(os.path.getmtime(fp))
            v += m
        except OSError:
            pass
    return v

@app.context_processor
def inject_static_version():
    return dict(static_version=_static_version())


def _clean_subcategory(category, subcategory, description=""):
    """Return the grocery subcategory for Groceries, else None.
    Accepts custom/free-form subcategories; auto-detects when blank."""
    if category != "Groceries":
        return None
    sub = (subcategory or "").strip()
    if sub:
        return sub
    return grocery_subcategory(description or "")


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


# ── SQL safety & fixes moved to services/sql_service.py ────
# (SqlService class) ──────────────────────────────────────────


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
@limiter.limit("10 per minute", key_func=get_remote_address)
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
@limiter.limit("5 per minute", key_func=get_remote_address)
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
@limiter.limit("3 per minute", key_func=get_remote_address)
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
@limiter.limit("5 per minute", key_func=get_remote_address)
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
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    today_expenses = db.get_expenses_by_date(today, user_id=uid)
    today_total = sum(e["amount"] for e in today_expenses)
    month_total = db.get_month_total(user_id=uid)
    for exp in today_expenses:
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    budget_status = db.get_budget_status(uid)
    budget_alerts = [b for b in budget_status if b["percentage"] >= 80]
    return jsonify({
        "today": today,
        "today_total": today_total,
        "month_total": month_total,
        "today_expenses": today_expenses,
        "category_colors": CATEGORY_COLORS,
        "grocery_subcategories": GROCERY_SUBCATEGORIES,
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
        "grocery_subcategories": GROCERY_SUBCATEGORIES,
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


@app.route("/api/admin/notifications/daily-digest/trigger", methods=["POST"])
@login_required
@superuser_required
def api_admin_trigger_digest():
    users = db.get_all_push_subscriptions()
    user_ids = sorted(set(u["user_id"] for u in users))
    user_sub_count = {uid: 0 for uid in user_ids}
    for sub in users:
        user_sub_count[sub["user_id"]] += 1
    sent = 0
    failed_endpoints = 0
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    for uid in user_ids:
        body = NotificationService.build_digest_body(uid)
        ok_count = NotificationService.send_push_notification(
            user_id=uid,
            title="📊 Daily Summary",
            body=body,
            tag="daily-digest",
            data={"type": "daily_digest"},
        )
        if ok_count:
            db.set_user_last_digest_sent(uid, today)
            sent += 1
        else:
            failed_endpoints += 1
    return jsonify({
        "sent": sent,
        "failed": failed_endpoints,
        "subscribed": len(user_ids),
        "vapid_loaded": NotificationService.is_vapid_configured(),
        "webpush_available": NotificationService.is_webpush_available(),
    })


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


# ── Q&A Pipeline moved to services/qa_service.py ──────────
# (QaService class) ──────────────────────────────────────────


# ── NL Q&A ──────────────────────────────────────────────────

@app.route("/api/ask", methods=["POST"])
@login_required
@limiter.limit("15 per minute")
def api_ask():
    data = request.get_json()
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question required"}), 400

    result = QaService.answer_question(
        question, data.get("history", []), session["user_id"],
    )
    if result is None:
        return jsonify({"error": "Could not answer this question"}), 500
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"type": "question", **result})


# ── Dynamic Suggestions ──────────────────────────────────────

@app.route("/api/suggestions", methods=["GET"])
@login_required
def api_suggestions():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)

    days_elapsed = now.day
    days_in_month = calendar.monthrange(now.year, now.month)[1]

    # ── Gather data ──
    cats = db.get_category_totals_by_month(now.year, now.month, uid)
    monthly = db.get_monthly_totals(2, uid)
    budgets = db.get_budget_status(uid)
    week_total = db.get_week_total(uid, week_start.isoformat(), today.isoformat())
    last_week_total = db.get_week_total(uid, last_week_start.isoformat(), (week_start - timedelta(days=1)).isoformat())

    month_total = sum(c["total"] for c in cats) if cats else 0
    daily_avg = round(month_total / days_elapsed, 0) if days_elapsed and month_total else 0

    pool = []

    # ── 1. Week-over-week ──
    if (week_total or last_week_total) and week_total != last_week_total:
        pool.append("How does this week compare to last week?")

    # ── 2. Month pacing ──
    if daily_avg and month_total:
        pool.append("Am I on track with my spending this month?")

    # ── 3. Month-over-month ──
    if len(monthly) >= 2:
        this_m = monthly[0]["total"]
        last_m = monthly[1]["total"]
        if last_m and this_m != last_m:
            pool.append("How does this month compare to last month?")

    # ── 4. Top category ──
    if cats:
        pool.append("What did I spend the most on this month?")

    # ── 5. Category with most transactions ──
    if cats:
        max_count = max(c["count"] for c in cats)
        if max_count >= 3:
            pool.append("Which category did I use the most this month?")

    # ── 6. Budget watch ──
    for b in sorted(budgets, key=lambda x: x["percentage"], reverse=True)[:2]:
        pct = b["percentage"]
        label = "Overall" if b["category"] == "__overall__" else b["category"]
        if pct >= 75:
            pool.append(f"Do I have budget left for {label}?")
        elif pct > 0:
            pool.append(f"How am I doing on {label} budget?")

    # ── 7. Unused categories ──
    used_cats = {c["category"] for c in cats}
    unused = [c for c in _ALL_CATEGORIES if c not in used_cats]
    if unused and len(used_cats) >= 5:
        pick = random.choice(unused)
        pool.append(f"Have I spent anything on {pick} this month?")

    # ── 8. Average transaction size ──
    if cats:
        total_count = sum(c["count"] for c in cats)
        avg_txn = round(month_total / total_count, 0) if total_count else 0
        if avg_txn:
            pool.append("What's my average expense size?")

    # ── 9. Biggest expense ──
    pool.append("What was my biggest expense this month?")

    # ── 10. Category breakdown ──
    if len(used_cats) >= 3:
        pool.append("Show me the breakdown by category")

    # ── 11. Top category "How much on X" ──
    for c in cats[:2]:
        pool.append(f"How much on {c['category']}?")

    # ── 12. Generic fallbacks ──
    pool.append("How does this week compare to last week?")
    pool.append("What's my average daily spending this month?")

    # Shuffle, deduplicate, return 4
    random.shuffle(pool)
    seen = set()
    unique = []
    for s in pool:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    return jsonify({"suggestions": unique[:4]})


# ── Chat (unified expense + Q&A) ──────────────────────────

@app.route("/api/chat", methods=["POST"])
@login_required
@limiter.limit("15 per minute")
def api_chat():
    data = request.get_json()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if len(message) < 2:
        return jsonify({"error": "Message required"}), 400

    message = QaService.normalize_question(message)

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
        items = split_expenses(cleaned_message, learned_categories=learned)
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
    result = QaService.answer_question(message, history, session["user_id"])
    if result is None:
        return jsonify({"error": "Could not answer this question"}), 500
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"type": "question", **result})


# ── Expense Splitting ──────────────────────────────────────

@app.route("/api/split_expense", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
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
        subcategory = _clean_subcategory(category, item.get("subcategory"), desc)

        # Auto-learn from confirmed split items
        for kw in extract_keywords(desc):
            db.learn_category(session["user_id"], kw, category)

        expense_id = db.add_expense(date, desc, amount, category, subcategory=subcategory, user_id=session["user_id"])
        saved.append({
            "id": expense_id,
            "date": date,
            "description": desc,
            "amount": amount,
            "category": category,
            "subcategory": subcategory,
            "color": CATEGORY_COLORS.get(category, "#6b7280"),
        })

    if not data.get("from_chat"):
        budget_alerts = db.get_budget_status(session["user_id"])
        budget_alerts = [b for b in budget_alerts if b["percentage"] >= 80]

        if budget_alerts:
            alerts_body = "; ".join(
                f"{a['category']} at {a['percentage']}% (৳{a['spent']:,.0f}/৳{a['budget_amount']:,.0f})"
                for a in budget_alerts
            )
            NotificationService.send_push_notification(
                user_id=session["user_id"],
                title="⚠️ Budget Alert",
                body=alerts_body,
                tag="budget-alert",
                data={"type": "budget", "alerts": budget_alerts},
            )
    else:
        budget_alerts = []

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
    subcategory = data.get("subcategory")

    if category and amount is not None and float(amount) > 0:
        amount = float(amount)
    else:
        result = extract_expense(description)
        category = result["category"]
        amount = result["amount"]
        subcategory = result.get("subcategory")

    if amount <= 0:
        return jsonify({"error": "Could not extract amount. Please include the amount in your text."}), 400

    subcategory = _clean_subcategory(category, subcategory, clean_desc)

    # Learn from user-corrected predictions
    if data.get("learn"):
        for kw in extract_keywords(clean_desc):
            db.learn_category(session["user_id"], kw, category)

    expense_id = db.add_expense(date, clean_desc, amount, category, subcategory=subcategory, user_id=session["user_id"])

    if not data.get("from_chat"):
        budget_alerts = db.get_budget_status(session["user_id"])
        budget_alerts = [b for b in budget_alerts if b["percentage"] >= 80]

        if budget_alerts:
            alerts_body = "; ".join(
                f"{a['category']} at {a['percentage']}% (৳{a['spent']:,.0f}/৳{a['budget_amount']:,.0f})"
                for a in budget_alerts
            )
            NotificationService.send_push_notification(
                user_id=session["user_id"],
                title="⚠️ Budget Alert",
                body=alerts_body,
                tag="budget-alert",
                data={"type": "budget", "alerts": budget_alerts},
            )
    else:
        budget_alerts = []

    return jsonify(
        {
            "id": expense_id,
            "date": date,
            "description": clean_desc,
            "amount": amount,
            "category": category,
            "subcategory": subcategory,
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
                "subcategory": result.get("subcategory"),
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


@app.route("/api/expenses/<int:expense_id>/unlink", methods=["POST"])
@login_required
def api_unlink_expense_from_session(expense_id):
    expense = db.get_expense_by_id(expense_id)
    if not expense:
        return jsonify({"error": "Expense not found"}), 404
    uid = session["user_id"]
    is_super = session.get("role") == "superuser"
    if not is_super and expense["user_id"] != uid:
        return jsonify({"error": "Forbidden"}), 403
    db.unlink_expense_from_session(expense_id)
    return jsonify({"success": True})


@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
@login_required
def api_update_expense(expense_id):
    expense = db.get_expense_by_id(expense_id)
    if not expense:
        return jsonify({"error": "Expense not found"}), 404

    uid = session["user_id"]
    is_super = session.get("role") == "superuser"
    if not is_super and expense["user_id"] != uid:
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json()
    description = data.get("description", "").strip()
    amount = data.get("amount")
    category = data.get("category", "").strip()
    subcategory = data.get("subcategory", "").strip()
    date = data.get("date", "").strip()

    if not description:
        return jsonify({"error": "Description required"}), 400
    if amount is not None and (not isinstance(amount, (int, float)) or float(amount) <= 0):
        return jsonify({"error": "Amount must be positive"}), 400
    if category and category not in CATEGORY_COLORS:
        return jsonify({"error": "Invalid category"}), 400
    if date and not date.strip():
        return jsonify({"error": "Invalid date"}), 400

    cleaned_subcategory = _clean_subcategory(category, subcategory or None, description)

    db.update_expense(
        expense_id,
        description=description,
        amount=float(amount) if amount is not None else None,
        category=category if category else None,
        subcategory=cleaned_subcategory,
        date=date if date else None,
    )

    updated = db.get_expense_by_id(expense_id)
    updated["color"] = CATEGORY_COLORS.get(updated["category"], "#6b7280")

    budget_alerts = []
    if updated["user_id"] == uid:
        status = db.get_budget_status(uid)
        budget_alerts = [b for b in status if b["percentage"] >= 80]

    return jsonify({
        **updated,
        "budget_alerts": budget_alerts,
    })


@app.route("/api/expenses/<int:expense_id>", methods=["GET"])
@login_required
def api_get_expense(expense_id):
    expense = db.get_expense_by_id(expense_id)
    if not expense:
        return jsonify({"error": "Expense not found"}), 404
    uid = session["user_id"]
    is_super = session.get("role") == "superuser"
    if not is_super and expense["user_id"] != uid:
        return jsonify({"error": "Forbidden"}), 403
    expense["color"] = CATEGORY_COLORS.get(expense["category"], "#6b7280")
    return jsonify(expense)


# ── Expense Sessions ──

_SESSION_ICONS = {
    "Food": "🍽️", "Groceries": "🛒", "Transport": "🚗", "Commute": "🚌",
    "Dining": "🍜", "Dining Out": "🍜", "Shopping": "🛍️", "Bills": "📄",
    "Entertainment": "🎬", "Health": "💊", "Medical": "💊", "Education": "📚",
    "Rent": "🏠", "Home": "🏠", "Fruits": "🍎", "Travel": "✈️",
    "Personal Care": "💇", "Gifts": "🎁", "Investment": "📈",
    "Savings": "💰", "Social": "🎉", "Errand": "📋", "Work": "💼",
    "Other": "📦",
}


def _format_single_reason(desc, category, amount):
    import re
    # Strip amount and currency from description
    clean = re.sub(r'\b\d+(?:\.\d+)?\s*(?:taka|tk|৳|টাকা)\b', '', desc, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\b(?:taka|tk|৳|টাকা)\s*\d+(?:\.\d+)?\b', '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s*\d+(?:\.\d+)?\s*$', '', clean).strip()
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean:
        clean = category

    # Map common Bangla/Banglish keywords to readable reasons
    kw = clean.lower()
    if category == "Rent" or any(w in kw for w in ("bhara", "ভাড়া", "rent", "basa", "bari", "flat", "house", "apartment", "mess")):
        return f"Monthly {clean} — ৳{amount:,.0f}"
    if category == "Bills" or any(w in kw for w in ("bill", "বিল", "electricity", "current", "gas", "water", "internet", "মোবাইল", "phone")):
        return f"{clean} — ৳{amount:,.0f}"
    if category in ("Health", "Medical") or any(w in kw for w in ("doctor", "pharmacy", "ওষুধ", "oshudh", "medicine", "hospital", "clinic")):
        return f"{clean} — ৳{amount:,.0f}"
    if category in ("Transport", "Commute") or any(w in kw for w in ("rickshaw", "bus", "টেম্পো", "tempo", "উবার", "uber", "পেট্রোল", "petrol", "fuel")):
        return f"Commute: {clean} — ৳{amount:,.0f}"
    if category == "Dining Out" or category == "Dining":
        return f"{clean} — ৳{amount:,.0f}"
    if category in ("Shopping", "Personal Care"):
        return f"{clean} — ৳{amount:,.0f}"
    if category == "Food":
        return f"{clean} — ৳{amount:,.0f}"
    if category == "Groceries":
        return f"{clean} — ৳{amount:,.0f}"

    return f"{clean} — ৳{amount:,.0f}"

@app.route("/api/sessions", methods=["GET"])
@login_required
def api_list_sessions():
    uid = session["user_id"]
    limit = request.args.get("limit", 20, type=int)
    sessions = db.get_user_sessions(uid, limit=limit)
    for s in sessions:
        s["total_amount"] = round(s["total_amount"], 2)
    return jsonify({"sessions": sessions})


@app.route("/api/sessions/generate", methods=["POST"])
@login_required
def api_generate_sessions():
    uid = session["user_id"]
    expenses = db.get_recent_unsessioned_expenses(uid, limit=50)
    if not expenses:
        return jsonify({"error": "No unsessioned expenses found"}), 400

    # Group by temporal proximity: within 2h windows
    expenses_sorted = sorted(expenses, key=lambda e: e.get("created_at", ""))
    groups = []
    current_group = [expenses_sorted[0]]
    for exp in expenses_sorted[1:]:
        t1 = current_group[-1].get("created_at", "")
        t2 = exp.get("created_at", "")
        try:
            dt1 = t1 if isinstance(t1, datetime) else datetime.strptime(t1, "%Y-%m-%d %H:%M:%S") if t1 else None
            dt2 = t2 if isinstance(t2, datetime) else datetime.strptime(t2, "%Y-%m-%d %H:%M:%S") if t2 else None
            if dt1 and dt2 and (dt2 - dt1).total_seconds() < 7200:
                current_group.append(exp)
            else:
                groups.append(current_group)
                current_group = [exp]
        except ValueError:
            groups.append(current_group)
            current_group = [exp]
    if current_group:
        groups.append(current_group)

    created = []
    for group in groups:
        if not group:
            continue
        # Single-expense groups: skip unless amount is large (>500)
        if len(group) == 1 and group[0]["amount"] < 500:
            continue

        # For single-expense groups, derive reason directly (faster, more accurate)
        if len(group) == 1:
            exp = group[0]
            category = exp.get("category", "Other")
            desc = exp.get("description", "").strip()
            amount = exp.get("amount", 0)
            reason = _format_single_reason(desc, category, amount)
            result = {
                "session_reason": reason,
                "reason_category": category,
                "icon": _SESSION_ICONS.get(category, "📦"),
                "expense_ids": [exp["id"]],
                "total_amount": amount,
                "start_time": exp.get("created_at", ""),
                "end_time": exp.get("created_at", ""),
                "confidence": "high",
            }
        else:
            result = extract_session_reason(group)
            if not result:
                continue

        sid = db.create_session(
            user_id=uid,
            reason=result["session_reason"],
            reason_category=result["reason_category"],
            icon=result["icon"],
            confidence=result["confidence"],
            total_amount=result["total_amount"],
            start_time=result["start_time"],
            end_time=result["end_time"],
            expense_ids=result["expense_ids"],
        )
        created.append({
            "id": sid,
            "reason": result["session_reason"],
            "icon": result["icon"],
            "total_amount": result["total_amount"],
            "count": len(group),
        })

    return jsonify({"created": len(created), "sessions": created})


@app.route("/api/sessions/<int:session_id>", methods=["GET"])
@login_required
def api_get_session(session_id):
    session_data = db.get_session_by_id(session_id)
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
    uid = session["user_id"]
    if session_data["user_id"] != uid and session.get("role") != "superuser":
        return jsonify({"error": "Forbidden"}), 403
    for exp in session_data.get("expenses", []):
        exp["color"] = CATEGORY_COLORS.get(exp["category"], "#6b7280")
    session_data["total_amount"] = round(session_data["total_amount"], 2)
    return jsonify(session_data)


@app.route("/api/sessions/<int:session_id>", methods=["PUT"])
@login_required
def api_update_session(session_id):
    session_data = db.get_session_by_id(session_id)
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
    uid = session["user_id"]
    if session_data["user_id"] != uid and session.get("role") != "superuser":
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json()
    db.update_session(
        session_id,
        reason=data.get("reason"),
        reason_category=data.get("reason_category"),
        icon=data.get("icon"),
        confidence=data.get("confidence"),
    )
    return jsonify({"success": True})


@app.route("/api/sessions/<int:session_id>", methods=["DELETE"])
@login_required
def api_delete_session(session_id):
    session_data = db.get_session_by_id(session_id)
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
    uid = session["user_id"]
    if session_data["user_id"] != uid and session.get("role") != "superuser":
        return jsonify({"error": "Forbidden"}), 403
    db.delete_session(session_id)
    return jsonify({"success": True, "unlinked": len(session_data.get("expenses", []))})


@app.route("/api/sessions/insights")
@login_required
def api_session_insights():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    insights = db.get_session_insights(uid, year, month)
    return jsonify({"insights": insights})


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
    response = dict(data)
    if category == "Groceries":
        response["subcategory_totals"] = db.get_subcategory_totals_by_month(
            year, month, category, user_id=effective_user_id
        )
    return jsonify(response)


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


# ── Recurring Transactions ─────────────────────────────────

@app.route("/api/recurring", methods=["GET", "POST"])
@login_required
def api_recurring():
    uid = session["user_id"]
    if request.method == "GET":
        transactions = db.get_recurring_transactions(uid)
        for t in transactions:
            t["color"] = CATEGORY_COLORS.get(t["category"], "#6b7280")
        return jsonify({"transactions": transactions})

    data = request.get_json()
    description = data.get("description", "").strip()
    amount = data.get("amount")
    category = data.get("category", "").strip()
    frequency = data.get("frequency", "monthly")
    next_date = data.get("next_date")
    end_date = data.get("end_date") or None
    interval_value = data.get("interval_value", 1)
    interval_unit = data.get("interval_unit")

    if not description:
        return jsonify({"error": "Description required"}), 400
    if not category:
        return jsonify({"error": "Category required"}), 400
    if not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400
    if not next_date:
        return jsonify({"error": "Next date required"}), 400

    rec_id = db.add_recurring(uid, description, amount, category, frequency, next_date, end_date, interval_value, interval_unit)
    return jsonify({"success": True, "id": rec_id})


@app.route("/api/recurring/<int:rec_id>", methods=["PUT"])
@login_required
def api_update_recurring(rec_id):
    data = request.get_json()
    allowed = ["description", "amount", "category", "frequency", "interval_value", "interval_unit", "next_date", "end_date", "is_active"]
    kwargs = {k: data[k] for k in allowed if k in data}
    db.update_recurring(rec_id, **kwargs)
    return jsonify({"success": True})


@app.route("/api/recurring/<int:rec_id>", methods=["DELETE"])
@login_required
def api_delete_recurring(rec_id):
    db.delete_recurring(rec_id)
    return jsonify({"success": True})


@app.route("/api/recurring/process", methods=["POST"])
@login_required
def api_process_recurring():
    uid = session["user_id"]
    due = db.get_due_recurring(uid)
    created = []
    for rec in due:
        exp_id = db.add_expense(rec["next_date"], rec["description"], rec["amount"], rec["category"], user_id=uid)
        next_date = db.compute_next_date(rec["next_date"], rec["frequency"], rec["interval_value"], rec["interval_unit"])
        db.update_next_date(rec["id"], next_date)
        created.append({"id": exp_id, "description": rec["description"], "amount": rec["amount"]})
    if created:
        NotificationService.send_push_notification(
            user_id=uid,
            title="🔄 Recurring Expenses Added",
            body=f"{len(created)} recurring expense(s) automatically created.",
            tag="recurring",
            data={"type": "recurring", "count": len(created)},
        )
    return jsonify({"processed": len(created), "expenses": created})


# ── Calendar: daily totals ─────────────────────────────────

@app.route("/api/expenses/daily-totals")
@login_required
def api_daily_totals():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)
    totals = db.get_daily_totals(year, month, user_id=uid)
    totals_map = {row["date"]: row["total"] for row in totals}
    return jsonify({"totals": totals_map, "year": year, "month": month})


# ── Push Notifications moved to services/notification_service.py ──
# (NotificationService class) ────────────────────────────────────


@app.route("/api/notifications/vapid-public-key", methods=["GET"])
def api_vapid_public_key():
    _, pub_key = NotificationService.load_vapid()
    if not pub_key:
        return jsonify({"error": "VAPID key not configured"}), 500
    return jsonify({"publicKey": pub_key})


@app.route("/api/notifications/subscribe", methods=["POST"])
@login_required
def api_subscribe():
    data = request.get_json()
    endpoint = data.get("endpoint", "").strip()
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh", "").strip()
    auth = keys.get("auth", "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "endpoint, p256dh, and auth required"}), 400
    db.save_push_subscription(session["user_id"], endpoint, p256dh, auth)
    return jsonify({"success": True})


@app.route("/api/notifications/unsubscribe", methods=["POST"])
@login_required
def api_unsubscribe():
    data = request.get_json()
    endpoint = data.get("endpoint", "").strip()
    if not endpoint:
        return jsonify({"error": "endpoint required"}), 400
    db.remove_push_subscription(session["user_id"], endpoint)
    return jsonify({"success": True})


@app.route("/api/notifications/check-digest", methods=["POST"])
@login_required
def api_check_digest():
    uid = session["user_id"]
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    last_sent = db.get_user_last_digest_sent(uid)
    if last_sent == today:
        return jsonify({"status": "already_sent"})
    subs = db.get_user_push_subscriptions(uid)
    if not subs:
        return jsonify({"status": "no_subscription"})
    body = NotificationService.build_digest_body(uid)
    ok_count = NotificationService.send_push_notification(
        user_id=uid,
        title="📊 Daily Summary",
        body=body,
        tag="daily-digest",
        data={"type": "daily_digest"},
    )
    if ok_count:
        db.set_user_last_digest_sent(uid, today)
        return jsonify({"status": "sent"})
    return jsonify({"status": "failed"})


@app.route("/api/notifications/daily-digest", methods=["POST"])
def api_daily_digest():
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret and request.args.get("key") != cron_secret:
        return jsonify({"error": "Unauthorized"}), 401
    users = db.get_all_push_subscriptions()
    user_ids = set(u["user_id"] for u in users)
    sent = 0
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    for uid in user_ids:
        body = NotificationService.build_digest_body(uid)
        ok_count = NotificationService.send_push_notification(
            user_id=uid,
            title="📊 Daily Summary",
            body=body,
            tag="daily-digest",
            data={"type": "daily_digest"},
        )
        if ok_count:
            db.set_user_last_digest_sent(uid, today)
            sent += 1
    return jsonify({"sent": sent})


# ── Spending Forecast ──────────────────────────────────────

@app.route("/api/forecast")
@login_required
def api_forecast():
    uid = session["user_id"]
    now = datetime.now(TIMEZONE)
    year = now.year
    month = now.month
    today = now.day
    days_in_month = calendar.monthrange(year, month)[1]

    daily_totals = db.get_daily_totals(year, month, user_id=uid)
    spent_so_far = sum(d["total"] for d in daily_totals)
    daily_avg = spent_so_far / today if today > 0 else 0
    linear_projected = daily_avg * days_in_month

    monthly_totals = db.get_monthly_totals(3, user_id=uid)
    current_month_str = f"{year}-{month:02d}"
    prev_month_total = None
    two_months_ago_total = None
    for mt in monthly_totals:
        if mt["month"] < current_month_str:
            if prev_month_total is None:
                prev_month_total = mt["total"]
            elif two_months_ago_total is None:
                two_months_ago_total = mt["total"]
                break

    category_breakdown = db.get_category_totals_by_month(year, month, user_id=uid)
    budget_status = db.get_budget_status(uid)
    overall_budget = None
    for b in budget_status:
        if b["category"] == "__overall__":
            overall_budget = b["budget_amount"]
            break

    # ── AI forecast ──
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    prev_month_daily_totals = db.get_daily_totals(prev_year, prev_month, user_id=uid)

    # Detect known fixed monthly expenses
    known_monthly_expenses = {"pending": [], "recorded": []}
    if prev_month_total:
        last_month_expenses = db.get_expenses_by_month(prev_year, prev_month, user_id=uid)
        from collections import Counter
        desc_counts = Counter()
        last_month_by_desc = {}
        for e in last_month_expenses:
            key = e["description"].strip().lower()
            desc_counts[key] += 1
            if key not in last_month_by_desc:
                last_month_by_desc[key] = {"description": e["description"], "category": e["category"], "amount": e["amount"]}

        current_month_expenses = db.get_expenses_by_month(year, month, user_id=uid)
        recorded_descs = set(e["description"].strip().lower() for e in current_month_expenses)

        for desc_key, info in last_month_by_desc.items():
            if desc_counts[desc_key] > 1:
                continue
            entry = {"description": info["description"], "category": info["category"], "amount": info["amount"]}
            if desc_key in recorded_descs:
                known_monthly_expenses["recorded"].append(entry)
            else:
                known_monthly_expenses["pending"].append(entry)

    ai_data = {
        "days_elapsed": today,
        "days_in_month": days_in_month,
        "spent_so_far": spent_so_far,
        "current_daily_totals": daily_totals,
        "prev_month_daily_totals": prev_month_daily_totals,
        "prev_month_total": prev_month_total,
        "two_months_ago_total": two_months_ago_total,
        "category_breakdown": category_breakdown,
        "overall_budget": overall_budget,
        "known_monthly_expenses": known_monthly_expenses,
    }
    ai_forecast = generate_forecast(ai_data)

    # Use AI projection if valid, otherwise fall back to linear
    if ai_forecast and isinstance(ai_forecast.get("projected"), (int, float)) and ai_forecast["projected"] > 0:
        projected = ai_forecast["projected"]
        confidence = ai_forecast.get("confidence", "medium")
        reasoning = ai_forecast.get("reasoning", "")
        best_case = ai_forecast.get("best_case")
        worst_case = ai_forecast.get("worst_case")
        notes = ai_forecast.get("notes", "")
    else:
        projected = linear_projected
        confidence = "low"
        reasoning = ""
        best_case = None
        worst_case = None
        notes = "Based on simple average (AI unavailable)"

    if overall_budget and overall_budget > 0:
        pct_of_budget = (projected / overall_budget) * 100
        if pct_of_budget > 100:
            status = "over"
            status_text = f"Projected to exceed ৳{overall_budget:,.0f} budget"
        elif pct_of_budget >= 90:
            status = "warning"
            status_text = f"Close to ৳{overall_budget:,.0f} budget limit"
        else:
            remaining = overall_budget - projected
            status = "under"
            status_text = f"On track — ৳{remaining:,.0f} under budget"
    else:
        status = "no_budget"
        status_text = "No budget set"

    vs_last_month = None
    if prev_month_total and prev_month_total > 0:
        diff = projected - prev_month_total
        pct = (diff / prev_month_total) * 100
        vs_last_month = {
            "diff": round(diff, 2),
            "pct": round(pct, 1),
            "direction": "up" if diff > 0 else "down",
        }

    return jsonify({
        "days_elapsed": today,
        "days_in_month": days_in_month,
        "spent_so_far": round(spent_so_far, 2),
        "daily_avg": round(daily_avg, 2),
        "projected": round(projected, 2),
        "overall_budget": round(overall_budget, 2) if overall_budget else None,
        "status": status,
        "status_text": status_text,
        "prev_month_total": round(prev_month_total, 2) if prev_month_total else None,
        "vs_last_month": vs_last_month,
        "ai": {
            "confidence": confidence,
            "reasoning": reasoning,
            "best_case": round(best_case, 2) if best_case else None,
            "worst_case": round(worst_case, 2) if worst_case else None,
            "notes": notes,
        },
    })


# ── Audio transcription ────────────────────────────────────

@app.route("/api/transcribe", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
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


# ── Receipt scanning ───────────────────────────────────────

ALLOWED_RECEIPT_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@app.route("/api/scan_receipt", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def api_scan_receipt():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    image = request.files["image"]
    if image.mimetype not in ALLOWED_RECEIPT_MIME:
        return jsonify({"error": "Unsupported image format"}), 400
    try:
        result = scan_receipt(image.read())
        if result.get("error"):
            return jsonify(result), 422
        if not result.get("items"):
            return jsonify({"error": "No items found in receipt", "items": []}), 422
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Scan failed: {type(e).__name__}: {e}"}), 500


# ── Service Worker (for push notifications & caching) ──────

@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js")


# ── SPA catch-all ─────────────────────────────────────────

@app.route("/")
@app.route("/<path:path>")
def spa_shell(path=None):
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
