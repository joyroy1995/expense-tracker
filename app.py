import os
import base64
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash
import re
import random
import calendar
import json
import sys
import database as db
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from llm_service import extract_expense, predict_expense, extract_keywords, generate_sql, correct_sql, answer_from_results, format_answer, split_expenses, _clean_split_desc, extract_date_reference, clean_date_refs, detect_budget_intent, is_question, transcribe_audio, decompose_question, compose_answers, generate_forecast
from database import _ALL_CATEGORIES
from config import USERNAME, PASSWORD, SECRET_KEY, CATEGORY_COLORS, TIMEZONE, SEED_CATEGORIES, VAPID_PRIVATE_KEY, VAPID_CLAIM_EMAIL

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_HTTPONLY=True,
)


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

# Known tables and columns for schema validation
_KNOWN_TABLES = {"expenses", "users", "budgets", "learned_categories", "password_resets"}
_KNOWN_COLUMNS = {
    "expenses": {"id", "date", "description", "amount", "category", "user_id", "created_at"},
    "users": {"id", "username", "password_hash", "role", "created_at"},
    "budgets": {"id", "user_id", "category", "amount", "created_at", "updated_at"},
}


def _validate_sql(sql):
    s = sql.strip()
    while s.endswith(";"):
        s = s[:-1].strip()
    # Reject multiple statements (semicolons within the query)
    if ";" in s:
        return False
    if not s.upper().startswith("SELECT"):
        return False
    if "--" in s or "/*" in s or "*/" in s:
        return False
    forbidden = {"DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE", "REPLACE", "EXEC"}
    words = re.findall(r'\b\w+\b', s.upper())
    for word in words:
        if word in forbidden:
            return False

    # Basic paren balancing
    if s.count("(") != s.count(")"):
        return False

    # Check referenced tables exist in known schema
    # Match table names after FROM/JOIN (excluding subqueries)
    table_refs = re.findall(r'(?:FROM|JOIN)\s+(\w+)', s, re.IGNORECASE)
    for t in table_refs:
        if t.lower() not in _KNOWN_TABLES:
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


def _fix_category_in_sql(sql, question):
    """Post-process generated SQL to fix wrong or missing category filters.
    Also strips spurious category filters when the question doesn't mention
    any category (e.g. contamination carried over from conversation history)."""
    question_lower = question.lower()
    mentioned = None
    for cat in sorted(_ALL_CATEGORIES, key=len, reverse=True):
        if cat.lower() in question_lower:
            mentioned = cat
            break
    if not mentioned:
        # No category mentioned — strip any spurious category filter
        # that may have been carried over from history.
        # Preserve __overall__ (budget pseudo-category).
        if re.search(r"(?:b\.)?category\s*=\s*'__overall__'", sql, re.IGNORECASE):
            return sql
        sql = re.sub(
            r'\s+AND\s+(?:b\.)?category\s*=\s*\'[^\']*\'',
            '', sql, flags=re.IGNORECASE,
        )
        sql = re.sub(
            r'\s+WHERE\s+(?:b\.)?category\s*=\s*\'[^\']*\' AND ',
            ' WHERE ', sql, flags=re.IGNORECASE,
        )
        return sql
    m = re.search(r"(?:b\.)?category\s*=\s*'([^']+)'", sql)
    if not m:
        # Question mentions a category but SQL has no category filter — add one
        insert_at = len(sql)
        for kw in [' GROUP BY ', ' ORDER BY ', ' LIMIT ', ' OFFSET ', ' HAVING ']:
            pos = sql.upper().find(kw)
            if pos != -1 and pos < insert_at:
                insert_at = pos
        sql = sql[:insert_at] + f" AND category = '{mentioned}'" + sql[insert_at:]
        return sql
    sql_cat = m.group(1)
    if sql_cat == mentioned or sql_cat == "__overall__":
        return sql
    sql = sql.replace(f"category = '{sql_cat}'", f"category = '{mentioned}'", 1)
    # Also fix b.category if present
    sql = sql.replace(f"b.category = '{sql_cat}'", f"b.category = '{mentioned}'", 1)
    return sql


def _fix_sort_order(sql, question):
    """Post-process SQL to add DESC when question asks for descending order."""
    if not re.search(r'\b(?:descending|desc|newest\s*first|reverse)\b', question, re.IGNORECASE):
        return sql
    sql_upper = sql.upper()
    idx = sql_upper.find('ORDER BY')
    if idx == -1:
        return sql
    rest = sql_upper[idx + 9:]
    if 'DESC' in rest:
        return sql
    insert_pos = len(sql)
    for kw in ['LIMIT', 'OFFSET', 'HAVING']:
        pos = rest.find(kw)
        if pos != -1 and (idx + 9 + pos) < insert_pos:
            insert_pos = idx + 9 + pos
    return sql[:insert_pos] + ' DESC ' + sql[insert_pos:].lstrip()


_SORT_COL_MAP = {
    'amount': 'amount', 'money': 'amount', 'spending': 'amount', 'cost': 'amount',
    'date': 'date', 'day': 'date', 'time': 'date',
    'category': 'category',
    'description': 'description', 'name': 'description', 'item': 'description',
}


def _fix_sort_column(sql, question):
    """Fix ORDER BY column when question explicitly says 'sort by X'."""
    m = re.search(r'(?:sort|order)\s+by\s+(\w+)', question, re.IGNORECASE)
    if not m:
        return sql
    col = m.group(1).lower()
    col = _SORT_COL_MAP.get(col)
    if not col:
        return sql
    if not re.search(r'ORDER\s+BY', sql, re.IGNORECASE):
        return sql
    sql = re.sub(
        r'ORDER\s+BY\s+\w+(\s+(?:ASC|DESC))?',
        f'ORDER BY {col} DESC',
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def _fix_frequency_sql(sql, question):
    """Post-process SQL to use COUNT(*) instead of SUM when user asks about frequency."""
    if not re.search(r'\b(?:frequency|how\s+many\s+times|how\s+often|most\s+frequent|most\s+used|use\s+the\s+most|used\s+the\s+most|count)\b', question, re.IGNORECASE):
        return sql
    sql_upper = sql.upper()
    # Only modify if the SQL uses SUM(amount) or SUM with a category GROUP BY
    if 'SUM' not in sql_upper and 'GROUP BY' not in sql_upper:
        return sql
    if 'COUNT(*)' in sql_upper or 'COUNT(1)' in sql_upper:
        return sql
    # Replace SUM(amount) 0 as total with COUNT(*) as count
    sql = re.sub(
        r'COALESCE\(\s*SUM\(\s*amount\s*\)\s*,\s*0\s*\)\s+as\s+total',
        'COUNT(*) as count',
        sql,
        flags=re.IGNORECASE
    )
    sql = re.sub(
        r'SUM\(\s*amount\s*\)\s+as\s+total',
        'COUNT(*) as count',
        sql,
        flags=re.IGNORECASE
    )
    # Fix ORDER BY: total DESC → count DESC
    sql = re.sub(r'ORDER\s+BY\s+total\s+DESC', 'ORDER BY count DESC', sql, flags=re.IGNORECASE)
    return sql


def _fix_top_n_limit(sql, question):
    """Fix LIMIT clause when question explicitly says 'top N' / 'last N' / 'N expenses'.
    Skips when N refers to a time period (e.g. 'last 7 days') rather than row count."""
    m = re.search(r'\b(top|last|first)\s+(\d+)\b', question, re.IGNORECASE)
    if not m:
        return sql
    # If followed by a time unit, it's a time period, not a row limit
    rest = question[m.end():].strip()
    if re.match(r'\b(day|days|week|weeks|month|months|year|years|hour|hours)\b', rest, re.IGNORECASE):
        return sql
    n = int(m.group(2))
    if 'LIMIT' in sql.upper():
        sql = re.sub(r'LIMIT\s+\d+', f'LIMIT {n}', sql, flags=re.IGNORECASE)
    return sql


def _fix_limit_syntax(sql, question):
    """Convert MySQL-style LIMIT a,b to PostgreSQL-compatible LIMIT b OFFSET a."""
    m = re.search(r'LIMIT\s+(\d+)\s*,\s*(\d+)', sql, re.IGNORECASE)
    if not m:
        return sql
    offset = m.group(1)
    limit = m.group(2)
    return sql[:m.start()] + f'LIMIT {limit} OFFSET {offset}' + sql[m.end():]


_ORDINAL_MAP = {
    'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
    'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
}


def _fix_ordinal_limit(sql, question):
    """Fix LIMIT+OFFSET when question asks for 'second most expensive' etc."""
    m = re.search(r'\b(second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\b', question, re.IGNORECASE)
    if not m:
        return sql
    word = m.group(1).lower()
    if word in _ORDINAL_MAP:
        n = _ORDINAL_MAP[word]
    else:
        n = int(re.sub(r'[^\d]', '', word))
    offset_val = n - 1
    singular = bool(re.search(r'\b(item|expense|transaction|purchase)\b', question, re.IGNORECASE) and
                    not re.search(r'\b(items|expenses|transactions|purchases)\b', question, re.IGNORECASE))
    if 'OFFSET' in sql.upper():
        if singular:
            sql = re.sub(r'LIMIT\s+\d+', 'LIMIT 1', sql, flags=re.IGNORECASE)
        sql = re.sub(r'OFFSET\s+\d+', f'OFFSET {offset_val}', sql, flags=re.IGNORECASE)
    else:
        if 'LIMIT' in sql.upper():
            if singular:
                sql = re.sub(r'LIMIT\s+\d+', f'LIMIT 1 OFFSET {offset_val}', sql, flags=re.IGNORECASE)
            else:
                sql = re.sub(r'LIMIT\s+\d+', f'LIMIT 50 OFFSET {offset_val}', sql, flags=re.IGNORECASE)
        else:
            limit_val = 1 if singular else 50
            sql += f' LIMIT {limit_val} OFFSET {offset_val}'
    return sql


def _fix_most_expensive_sql(sql, question):
    """Add ORDER BY amount DESC LIMIT 1 when question asks for the single
    most expensive expense (LLM may omit sort/limit for 'most' queries)."""
    q = question.lower()
    if not re.search(r'\b(?:most\s+expensive|biggest\s+expense|largest\s+expense)\b', q):
        return sql
    if re.search(r'\bORDER\s+BY\b', sql, re.IGNORECASE):
        return sql
    if re.search(r'\b(?:SUM|COUNT|AVG|COALESCE)\s*\(', sql, re.IGNORECASE):
        return sql
    if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
        return sql
    sql = sql.rstrip().rstrip(';').strip()
    sql += ' ORDER BY amount DESC LIMIT 1'
    return sql


def _fix_category_breakdown_sql(sql, question):
    """Convert plain list SQL to category breakdown when question asks for
    breakdown by category (LLM may generate a flat list instead)."""
    q = question.lower()
    if not re.search(r'\b(?:breakdown\s+by\s+category|category\s+breakdown|by\s+category|which\s+category|spend\s+the\s+most\s+on|spent\s+the\s+most\s+on|category\s+wise|per\s+category|group\s+by\s+category|top\s+\d+\s+categor(?:y|ies)\s+by|categories?\s+by\s+spending)\b', q):
        return sql
    if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
        return sql
    parts = re.split(r'\bFROM\b', sql, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) < 2:
        return sql
    from_clause = parts[1].strip()
    for kw in [' ORDER BY ', ' LIMIT ', ' OFFSET ', ' HAVING ']:
        pos = from_clause.upper().find(kw)
        if pos != -1:
            from_clause = from_clause[:pos]
    return f"SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM {from_clause} GROUP BY category ORDER BY total DESC"


def _fix_history_id_filter(sql, question):
    """Strip stale id exclusion filters left over from history context.
    Removes AND id != N / AND expenses.id != N / AND e.id != N patterns
    when the current question does NOT contain unambiguous exclusion keywords.
    Bare 'other' is intentionally excluded since it matches the 'Other' category."""
    exclusion_kw = re.search(r'\b(?:other\s+than|except|excluding|exclude|not\s+including|without|but\s+not|aside\s+from)\b', question, re.IGNORECASE)
    if exclusion_kw:
        return sql
    sql = re.sub(
        r'\s+AND\s+(?:expenses\.|e\.)?id\s*!=\s*\d+',
        '',
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def _fix_date_filter(sql, question):
    """Fix date filter to use exact date when question mentions a specific date.
    Replaces date LIKE 'YYYY-MM%'  with date = 'YYYY-MM-DD' when the
    question contains a YYYY-MM-DD literal or 'on <date>' pattern."""
    m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', question)
    if m:
        exact_date = m.group(0)
        month_pattern = exact_date[:7]  # YYYY-MM
        sql = re.sub(
            rf"date\s+LIKE\s*'{re.escape(month_pattern)}%'",
            f"date = '{exact_date}'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            rf"date\s*>=\s*'{exact_date}'\s+AND\s+date\s*<=\s*'{exact_date}'",
            f"date = '{exact_date}'",
            sql,
            flags=re.IGNORECASE,
        )

    # Reverse: expand exact date to month filter when question is about a month
    # but the SQL uses a single date (LLM may use {today} instead of {current_month})
    if re.search(r'\b(?:this\s+month|last\s+month|current\s+month)\b', question, re.IGNORECASE):
        sql = re.sub(
            r"date\s*=\s*'(\d{4})-(\d{2})-\d{2}'",
            r"date LIKE '\1-\2%'",
            sql,
            flags=re.IGNORECASE,
        )

    # Fix: when question asks about "today"/"yesterday", override the date in SQL
    if re.search(r'\btoday\b', question, re.IGNORECASE):
        today_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        sql = re.sub(
            r"date\s*=\s*'\d{4}-\d{2}-\d{2}'",
            f"date = '{today_str}'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"date\s+LIKE\s*'\d{4}-\d{2}%'",
            f"date = '{today_str}'",
            sql,
            flags=re.IGNORECASE,
        )
    elif re.search(r'\byesterday\b|\blast\s+(?:day|date|night|evening|morning|afternoon)\b', question, re.IGNORECASE):
        yesterday_str = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
        sql = re.sub(
            r"date\s*=\s*'\d{4}-\d{2}-\d{2}'",
            f"date = '{yesterday_str}'",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"date\s+LIKE\s*'\d{4}-\d{2}%'",
            f"date = '{yesterday_str}'",
            sql,
            flags=re.IGNORECASE,
        )

    return sql


def _fix_show_expenses_aggregate(sql, question):
    """Rewrite aggregate queries to individual records when user asks to 'show expenses'
    or asks about a specific expense item (e.g. 'which date i bought X')."""
    q = question.lower()
    show_intent = bool(re.search(r'\b(?:show|list|display)\b', q)) or \
                  bool(re.search(r'\bwhat\s+(?:are|were|is|was)\b.*\b(?:expense|transaction|record)', q))
    # Detect item lookup: "which date/day did I buy X", "when did I buy X"
    item_intent = bool(re.search(r'\b(?:which\s+(?:date|day)|when)\b', q)) and \
                  bool(re.search(r'\b(?:bought|buy|purchase|purchased|get|got)\b', q))
    if not show_intent and not item_intent:
        return sql
    if show_intent:
        if not re.search(r'\b(?:expense|expenses|transaction|transactions|record|records)\b', q):
            return sql
        if re.search(r'\b(?:how\s+much|total|sum|amount|spent|spend)\b', q):
            return sql
    if not re.search(r'\b(?:SUM|COUNT|AVG|COALESCE)\s*\(', sql, re.IGNORECASE):
        return sql
    if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
        return sql
    parts = re.split(r'\bFROM\b', sql, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) < 2:
        return sql
    return f"SELECT id, date, description, category, amount FROM {parts[1].strip()}"


_SKIP_WORDS = frozenset({'all', 'my', 'your', 'the', 'this', 'that', 'these', 'those', 'show',
                          'list', 'get', 'give', 'find', 'see', 'view', 'display', 'print',
                          'any', 'some', 'every', 'each', 'total', 'month', 'day', 'week', 'year',
                          'biggest', 'largest', 'smallest', 'cheapest', 'most', 'least',
                          'highest', 'lowest', 'best', 'worst', 'recent', 'last', 'first',
                          'previous', 'next', 'top', 'bottom',
                          'today', 'todays', 'tonight', 'yesterday', 'yesterdays'})


def _extract_item_keyword(q):
    """Extract a potential item keyword from a question for description LIKE filtering."""
    # Pattern 1: "bought/buy/purchase X"
    m = re.search(r'\b(?:bought|buy|purchase|purchased|get|got)\s+(?:a\s+|an\s+|the\s+|some\s+)?(\w+)', q)
    if m:
        word = m.group(1).strip()
        if word not in _SKIP_WORDS:
            return word
    # Pattern 2: "spent/spend on X" or "spent on X fare/ticket/etc"
    m = re.search(r'\b(?:spent|spend)\s+on\s+(?:a\s+|an\s+|the\s+)?(\w+(?:\s+\w+)?)', q)
    if m:
        word = m.group(1).strip().split()[0]
        if word not in _SKIP_WORDS:
            return word
    # Pattern 3: "on X" after "how much" (e.g. "how much on rickshaw")
    m = re.search(r'\bhow\s+much\s+(?:on|for)\s+(?:a\s+|an\s+|the\s+)?(\w+)', q)
    if m:
        word = m.group(1).strip()
        if word not in _SKIP_WORDS:
            return word
    # Pattern 4: "X expenses" — word right before "expenses/expense" (e.g. "rickshaw expenses")
    m = re.search(r'\b(\w+)\s+expenses?\b', q)
    if m:
        word = m.group(1).strip()
        if word not in _SKIP_WORDS:
            return word
    return None

def _fix_description_filter(sql, question):
    """If the question mentions a specific item and the SQL lacks a description LIKE filter, add one."""
    q = question.lower()
    if re.search(r"description\s+LIKE", sql, re.IGNORECASE):
        return sql
    if re.search(r"category\s*=", sql, re.IGNORECASE):
        return sql
    keyword = _extract_item_keyword(q)
    if not keyword or len(keyword) < 2 or keyword in [c.lower() for c in _ALL_CATEGORIES] or keyword.endswith('est'):
        return sql
    insert_at = len(sql)
    for kw in [' ORDER BY ', ' GROUP BY ', ' LIMIT ', ' OFFSET ', ' HAVING ']:
        pos = sql.upper().find(kw)
        if pos != -1 and pos < insert_at:
            insert_at = pos
    clause = f" AND LOWER(description) LIKE '%{keyword}%'"
    return sql[:insert_at] + clause + sql[insert_at:]


def _fix_aggregate_sql(sql, question):
    """Convert list queries to aggregate when question asks for total/amount/sum/how much."""
    q = question.lower()
    if not re.search(r'\b(?:how\s+much|total|sum|amount)\b', q):
        return sql
    if re.search(r'\b(?:SUM|COUNT|AVG|COALESCE)\s*\(', sql, re.IGNORECASE):
        return sql
    if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
        return sql
    parts = re.split(r'\bFROM\b', sql, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) < 2:
        return sql
    from_clause = parts[1].strip()
    for kw in [' ORDER BY ', ' LIMIT ', ' OFFSET ']:
        pos = from_clause.upper().find(kw)
        if pos != -1:
            from_clause = from_clause[:pos]
    return f"SELECT COALESCE(SUM(amount), 0) as total FROM {from_clause}"


def _fix_budget_query(sql, question):
    """Replace SQL with a proper budget query when the question asks about budget
    but the generated SQL doesn't reference the budgets table."""
    q = question.lower()
    if not re.search(r'\bbudget\b', q):
        return sql
    if 'budgets' in sql.lower():
        return sql

    month = datetime.now(TIMEZONE).strftime("%Y-%m")
    m = re.search(r"date\s+LIKE\s+'(\d{4}-\d{2})%'", sql)
    if m:
        month = m.group(1)

    mentioned_cat = None
    for cat in sorted(_ALL_CATEGORIES, key=len, reverse=True):
        if cat.lower() in q:
            mentioned_cat = cat
            break

    if mentioned_cat:
        return f"SELECT b.category, b.amount as budget_amount, COALESCE(SUM(e.amount), 0) as spent, b.amount - COALESCE(SUM(e.amount), 0) as remaining FROM budgets b LEFT JOIN expenses e ON e.user_id = b.user_id AND e.category = b.category AND e.date LIKE '{month}%' WHERE b.user_id = :uid AND b.category = '{mentioned_cat}' GROUP BY b.id, b.category, b.amount"

    return f"SELECT b.category, b.amount as budget_amount, (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{month}%') as spent, (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{month}%') as remaining FROM budgets b WHERE b.user_id = :uid AND b.category = '__overall__'"


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
    for uid in user_ids:
        yesterday = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
        month = datetime.now(TIMEZONE).strftime("%Y-%m")
        conn = db.get_connection()
        y_row = conn.execute(
            db.text("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date = :d"),
            {"uid": uid, "d": yesterday},
        ).fetchone()
        m_row = conn.execute(
            db.text("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND SUBSTR(date, 1, 7) = :m"),
            {"uid": uid, "m": month},
        ).fetchone()
        yesterday_total = y_row[0] if y_row else 0
        month_total = m_row[0] if m_row else 0
        body_parts = []
        if yesterday_total > 0:
            body_parts.append(f"Yesterday: ৳{yesterday_total:,.0f}")
        body_parts.append(f"Month to date: ৳{month_total:,.0f}")
        ok_count = send_push_notification(
            user_id=uid,
            title="📊 Daily Summary",
            body=" | ".join(body_parts),
            tag="daily-digest",
            data={"type": "daily_digest"},
        )
        if ok_count:
            sent += 1
        else:
            failed_endpoints += 1
    return jsonify({
        "sent": sent,
        "failed": failed_endpoints,
        "subscribed": len(user_ids),
        "vapid_loaded": _vapid_instance is not None,
        "webpush_available": _pywebpush_available,
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


# ── Shared Q&A Pipeline ──────────────────────────────────

def _normalize_question(text):
    """Normalize shorthand comparison queries to match SQL_PROMPT examples."""
    if re.search(r'\bhow\s+does\s+this\s+month\s+compare\b', text, re.IGNORECASE):
        return text
    text = re.sub(
        r'\bcompare\s+(?:to|with)\s+last\s+month\b',
        'How does this month compare to last month',
        text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\bcompare\s+(?:to|with)\s+previous\s+month\b',
        'How does this month compare to last month',
        text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\bthis\s+month\s+vs\.?\s+last\s+month\b',
        'How does this month compare to last month',
        text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\bmonth\s+over\s+month\b',
        'How does this month compare to last month',
        text, flags=re.IGNORECASE,
    )
    return text


def _run_qa_pipeline(question, question_with_context, schema, history, uid, force_programmatic=False):
    """Run a single question through SQL pipeline: cache→generate→validate→execute→format.
    Returns dict with answer/sql/data/columns, or dict with error key."""
    cached = db.get_cached_sql(question_with_context, schema)
    if cached:
        sql = cached["sql"]
    else:
        try:
            sql = generate_sql(question_with_context, schema, history=history)
        except Exception as e:
            return {"error": f"LLM query failed: {str(e)}"}
        if not sql:
            return {"error": "Could not generate SQL query. Check API key."}
        db.cache_qa_sql(question_with_context, sql, schema)

    if not _validate_sql(sql):
        return {"error": "Generated query is not a valid SELECT statement", "sql": sql}

    sql = _ensure_user_filter(sql)
    sql = _fix_category_in_sql(sql, question)
    sql = _fix_sort_order(sql, question)
    sql = _fix_sort_column(sql, question)
    sql = _fix_frequency_sql(sql, question)
    sql = _fix_top_n_limit(sql, question)
    sql = _fix_limit_syntax(sql, question)
    sql = _fix_ordinal_limit(sql, question)
    sql = _fix_category_breakdown_sql(sql, question)
    sql = _fix_aggregate_sql(sql, question)
    sql = _fix_most_expensive_sql(sql, question)
    sql = _fix_history_id_filter(sql, question)
    sql = _fix_date_filter(sql, question)
    sql = _fix_show_expenses_aggregate(sql, question)
    sql = _fix_description_filter(sql, question)
    sql = _fix_budget_query(sql, question)

    try:
        conn = db.get_connection()
        result = conn.execute(db.text(sql), {"uid": uid})
        columns = list(result.keys()) if result.returns_rows else []
        rows = result.fetchmany(50)
        rows_data = [dict(r._mapping) for r in rows]
    except Exception as e:
        corrected = correct_sql(sql, str(e), schema, question_with_context, history=history)
        if corrected and _validate_sql(corrected):
            corrected = _ensure_user_filter(corrected)
            corrected = _fix_category_in_sql(corrected, question)
            corrected = _fix_sort_order(corrected, question)
            corrected = _fix_sort_column(corrected, question)
            corrected = _fix_frequency_sql(corrected, question)
            corrected = _fix_top_n_limit(corrected, question)
            corrected = _fix_limit_syntax(corrected, question)
            corrected = _fix_ordinal_limit(corrected, question)
            corrected = _fix_category_breakdown_sql(corrected, question)
            corrected = _fix_aggregate_sql(corrected, question)
            corrected = _fix_most_expensive_sql(corrected, question)
            corrected = _fix_history_id_filter(corrected, question)
            corrected = _fix_date_filter(corrected, question)
            corrected = _fix_show_expenses_aggregate(corrected, question)
            corrected = _fix_description_filter(corrected, question)
            corrected = _fix_budget_query(corrected, question)
            try:
                conn2 = db.get_connection()
                result = conn2.execute(db.text(corrected), {"uid": uid})
                columns = list(result.keys()) if result.returns_rows else []
                rows = result.fetchmany(50)
                rows_data = [dict(r._mapping) for r in rows]
                sql = corrected
            except Exception:
                return {"error": f"Query execution failed: {str(e)}", "sql": sql, "corrected_sql": corrected}
        else:
            return {"error": f"Query execution failed: {str(e)}", "sql": sql}

    if _needs_llm_answer(question) and not force_programmatic:
        answer = answer_from_results(question, sql, rows_data[:20], history=history)
        if not answer:
            answer = format_answer(columns, rows_data, question)
    else:
        answer = format_answer(columns, rows_data, question)

    return {"answer": answer, "sql": sql, "data": rows_data[:50], "columns": columns}


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
    "budget", "budget left", "budget remaining", "exceed", "overspend",
    "remaining", "left",
    "percentage", "percent", "ratio",
    "change", "growth", "decline",
    "average", "avg", "mean",
    "highest", "lowest", "most", "least", "top", "bottom",
    "do i spend more", "do i spend less",
    "on track", "how am i doing",
    "monthly comparison", "month over month",
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

    question = _normalize_question(question)

    history = data.get("history", [])

    schema = _get_schema_cached()
    current_date = datetime.now(TIMEZONE).strftime("%B %d, %Y")
    cleaned_for_date, expense_date = extract_date_reference(question, datetime.now(TIMEZONE))
    date_context = f"Today is {current_date}."
    if expense_date:
        date_context += f" The user is referring to date {expense_date}."
    question_with_context = f"{date_context}\n\nQuestion: {cleaned_for_date}"

    # Try decomposition
    sub_questions = decompose_question(question_with_context, schema, history=history)

    if sub_questions:
        sub_results = []
        for sq in sub_questions:
            sq_with_context = f"{date_context}\n\nQuestion: {sq}"
            result = _run_qa_pipeline(sq, sq_with_context, schema, history, session["user_id"], force_programmatic=True)
            if "error" not in result:
                result["sub_question"] = sq
                sub_results.append(result)

        if not sub_results:
            return jsonify({"error": "Could not answer this question"}), 500

        answer = compose_answers(question, sub_results, history=history)
        if not answer:
            answer = " ".join(r["answer"] for r in sub_results if r.get("answer"))

        all_sql = "; ".join(r["sql"] for r in sub_results if r.get("sql"))
        all_data = []
        seen = set()
        for r in sub_results:
            for row in r.get("data", []):
                k = tuple(sorted(row.items()))
                if k not in seen:
                    seen.add(k)
                    all_data.append(row)

        return jsonify({
            "answer": answer,
            "sql": all_sql,
            "data": all_data[:50],
            "columns": sub_results[0].get("columns", []) if sub_results else [],
            "decomposed": True,
        })

    result = _run_qa_pipeline(question, question_with_context, schema, history, session["user_id"])
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)


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
def api_chat():
    data = request.get_json()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if len(message) < 2:
        return jsonify({"error": "Message required"}), 400

    message = _normalize_question(message)

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
    schema = _get_schema_cached()
    current_date = datetime.now(TIMEZONE).strftime("%B %d, %Y")
    date_context = f"Today is {current_date}."
    if expense_date:
        date_context += f" The user is referring to date {expense_date}."
    question_with_context = f"{date_context}\n\nQuestion: {cleaned_message}"

    # Try decomposition
    sub_questions = decompose_question(question_with_context, schema, history=history)

    if sub_questions:
        sub_results = []
        for sq in sub_questions:
            sq_with_context = f"{date_context}\n\nQuestion: {sq}"
            result = _run_qa_pipeline(sq, sq_with_context, schema, history, session["user_id"], force_programmatic=True)
            if "error" not in result:
                result["sub_question"] = sq
                sub_results.append(result)

        if not sub_results:
            return jsonify({"error": "Could not answer this question"}), 500

        answer = compose_answers(message, sub_results, history=history)
        if not answer:
            answer = " ".join(r["answer"] for r in sub_results if r.get("answer"))

        all_sql = "; ".join(r["sql"] for r in sub_results if r.get("sql"))
        all_data = []
        seen = set()
        for r in sub_results:
            for row in r.get("data", []):
                k = tuple(sorted(row.items()))
                if k not in seen:
                    seen.add(k)
                    all_data.append(row)

        return jsonify({
            "type": "question",
            "answer": answer,
            "sql": all_sql,
            "data": all_data[:50],
            "columns": sub_results[0].get("columns", []) if sub_results else [],
            "decomposed": True,
        })

    result = _run_qa_pipeline(message, question_with_context, schema, history, session["user_id"])
    if "error" in result:
        return jsonify(result), 500
    return jsonify({"type": "question", **result})


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

    if budget_alerts:
        alerts_body = "; ".join(
            f"{a['category']} at {a['percentage']}% (৳{a['spent']:,.0f}/৳{a['budget_amount']:,.0f})"
            for a in budget_alerts
        )
        send_push_notification(
            user_id=session["user_id"],
            title="⚠️ Budget Alert",
            body=alerts_body,
            tag="budget-alert",
            data={"type": "budget", "alerts": budget_alerts},
        )

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

    if budget_alerts:
        alerts_body = "; ".join(
            f"{a['category']} at {a['percentage']}% (৳{a['spent']:,.0f}/৳{a['budget_amount']:,.0f})"
            for a in budget_alerts
        )
        send_push_notification(
            user_id=session["user_id"],
            title="⚠️ Budget Alert",
            body=alerts_body,
            tag="budget-alert",
            data={"type": "budget", "alerts": budget_alerts},
        )

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
        send_push_notification(
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


# ── Push Notifications ─────────────────────────────────────

_vapid_instance = None
_pywebpush_available = None
_vapid_public_key_cache = None
_webpush_func = None  # cached reference to pywebpush.webpush

def _load_vapid():
    global _vapid_instance, _vapid_public_key_cache
    if _vapid_instance is not None:
        return _vapid_instance, _vapid_public_key_cache
    try:
        key_bytes = VAPID_PRIVATE_KEY.encode()
        # Try py_vapid first (pywebpush natively supports Vapid instances)
        try:
            from py_vapid import Vapid
            _vapid_instance = Vapid.from_pem(key_bytes)
        except ImportError:
            _vapid_instance = serialization.load_pem_private_key(
                key_bytes, password=None, backend=default_backend()
            )
        # Derive public key for client subscription
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
        if isinstance(_vapid_instance, EllipticCurvePrivateKey):
            raw_pub = _vapid_instance.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        else:
            raw_pub = _vapid_instance.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        _vapid_public_key_cache = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
        return _vapid_instance, _vapid_public_key_cache
    except Exception as e:
        print(f"[push] Failed to load VAPID key: {e}", file=sys.stderr)
        _vapid_instance = None
        _vapid_public_key_cache = None
        return None, None

def send_push_notification(user_id, title, body, icon=None, tag=None, data=None):
    """Send push notification to all subscriptions of a user.
    Returns number of successful sends."""
    if not VAPID_PRIVATE_KEY or not VAPID_CLAIM_EMAIL:
        return 0
    global _pywebpush_available, _webpush_func
    if _pywebpush_available is None:
        try:
            from pywebpush import webpush
            _webpush_func = webpush
            _pywebpush_available = True
        except ImportError:
            _pywebpush_available = False
            return 0
    if not _pywebpush_available or _webpush_func is None:
        return 0
    vapid_key, _ = _load_vapid()
    if vapid_key is None:
        return 0
    subs = db.get_user_push_subscriptions(user_id)
    if not subs:
        return 0
    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon or "/static/icon-192.png",
        "badge": "/static/icon-192.png",
        "tag": tag or "default",
        "data": data or {},
    })
    ok_count = 0
    for sub in subs:
        try:
            _webpush_func(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh_key"], "auth": sub["auth_key"]},
                },
                data=payload,
                vapid_private_key=vapid_key,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL},
            )
            ok_count += 1
        except Exception as e:
            print(f"[push] Failed to send to user {user_id}: {type(e).__name__}: {e}", file=sys.stderr)
            err_str = str(e)
            if "410" in err_str or "404" in err_str or "gone" in err_str.lower() or "unregistered" in err_str.lower():
                try:
                    db.remove_push_subscription(user_id, sub["endpoint"])
                except Exception:
                    pass
    return ok_count


@app.route("/api/notifications/vapid-public-key", methods=["GET"])
def api_vapid_public_key():
    _, pub_key = _load_vapid()
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


@app.route("/api/notifications/daily-digest", methods=["POST"])
def api_daily_digest():
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret and request.args.get("key") != cron_secret:
        return jsonify({"error": "Unauthorized"}), 401
    users = db.get_all_push_subscriptions()
    user_ids = set(u["user_id"] for u in users)
    sent = 0
    for uid in user_ids:
        yesterday = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
        month = datetime.now(TIMEZONE).strftime("%Y-%m")
        conn = db.get_connection()
        y_row = conn.execute(
            db.text("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date = :d"),
            {"uid": uid, "d": yesterday},
        ).fetchone()
        m_row = conn.execute(
            db.text("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND SUBSTR(date, 1, 7) = :m"),
            {"uid": uid, "m": month},
        ).fetchone()
        yesterday_total = y_row[0] if y_row else 0
        month_total = m_row[0] if m_row else 0
        body_parts = []
        if yesterday_total > 0:
            body_parts.append(f"Yesterday: ৳{yesterday_total:,.0f}")
        body_parts.append(f"Month to date: ৳{month_total:,.0f}")
        ok_count = send_push_notification(
            user_id=uid,
            title="📊 Daily Summary",
            body=" | ".join(body_parts),
            tag="daily-digest",
            data={"type": "daily_digest"},
        )
        if ok_count:
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
