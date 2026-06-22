import hashlib
import json
import re
from datetime import datetime
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection, get_data_version, bump_data_version


_ALL_CATEGORIES = [
    "Bills", "Dining Out", "Education", "Entertainment", "Food",
    "Fruits", "Gifts", "Groceries", "Health", "Investment",
    "Other", "Personal Care", "Rent", "Savings", "Shopping",
    "Transport", "Travel",
]

SCHEMA_VERSION = 3

OVERALL_BUDGET_CATEGORY = "__overall__"

_RESPONSE_CACHE_TTL_SECONDS = 60

_STOP_WORDS = frozenset({
    "me", "my", "the", "a", "an", "did", "do", "does", "is", "are",
    "was", "were", "of", "in", "on", "at", "to", "for", "with",
    "how", "what", "why", "show", "tell", "list", "give", "which",
    "when", "where", "who", "all", "total", "spending", "expenses",
    "much", "many", "please", "can", "could", "would", "will",
    "am", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "but", "or", "if", "so", "up", "down", "out", "just",
    "about", "than", "too", "also", "very", "some", "any", "every",
    "overall",
})


def _normalize_question(q):
    q = q.lower()
    q = re.sub(r'[^\w\s]', ' ', q)
    q = re.sub(r'\s+', ' ', q).strip()
    tokens = [w for w in q.split() if w not in _STOP_WORDS and len(w) > 1]
    return ' '.join(sorted(set(tokens)))


def _schema_hash(schema_str):
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]


def get_schema():
    conn = get_connection()
    db_cats = conn.execute(
        text("SELECT DISTINCT category FROM expenses ORDER BY category")
    ).fetchall()
    db_cat_set = {r[0] for r in db_cats}
    all_cats = sorted(db_cat_set | set(_ALL_CATEGORIES))
    cats_str = ", ".join(f"'{c}'" for c in all_cats)
    budget_cats = conn.execute(
        text("SELECT DISTINCT category FROM budgets ORDER BY category")
    ).fetchall()
    budget_cats_display = [("__overall__ (Overall total spending)" if r[0] == OVERALL_BUDGET_CATEGORY else r[0]) for r in budget_cats]
    budget_cats_str = ", ".join(budget_cats_display) if budget_cats_display else "none set"

    range_row = conn.execute(
        text("SELECT MIN(date) as first, MAX(date) as last FROM expenses")
    ).fetchone()
    date_range = ""
    if range_row and range_row[0] and range_row[1]:
        date_range = f" (data ranges from {range_row[0]} to {range_row[1]})"

    return f"""
Table: expenses (main table — stores all expense transactions) [schema v{SCHEMA_VERSION}]
Columns:
- id (INTEGER): primary key
- date (TEXT): YYYY-MM-DD format{date_range}
- description (TEXT): expense description in Banglish/Bengali/English
- amount (REAL): amount in BDT (always positive)
- category (TEXT): use exact value in WHERE: {cats_str}
- user_id (INTEGER): foreign key → users.id — owner of the expense
- created_at (TEXT): timestamp when recorded
Relationships: expenses.user_id → users.id (each expense belongs to a user)

Table: users
Columns:
- id (INTEGER): primary key
- username (TEXT): login name
- password_hash (TEXT): hashed password (not queryable)
- role (TEXT): 'user' or 'superuser'
- created_at (TEXT): timestamp
Relationships: users.id ← expenses.user_id (a user has many expenses)
             users.id ← budgets.user_id (a user has many budgets)

Table: budgets (recurring monthly spending limits — one row per category per user)
Columns:
- id (INTEGER): primary key
- user_id (INTEGER): foreign key → users.id — owner of the budget
- category (TEXT): use exact value in WHERE: {budget_cats_str}
- amount (REAL): monthly budget amount in BDT
- created_at (TEXT): timestamp when set
- updated_at (TEXT): timestamp when last updated
Relationships: budgets.user_id → users.id (each budget belongs to a user)
Semantics: budgets are recurring monthly limits. A budget resets each month.
           To compare spending vs budget in a given month, LEFT JOIN budgets → expenses
           on user_id AND category AND SUBSTR(expenses.date, 1, 7) = target_month.
           The special category '__overall__' in budgets represents the total spending
           budget across ALL categories. For '__overall__', do NOT join on e.category.
           Instead, use a scalar subquery to sum ALL expenses for the month:
           (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid
            AND date LIKE 'YYYY-MM%') as spent.
"""


def cache_response(question, sql, response_data, answer, schema_str):
    conn = get_connection()
    normalized = _normalize_question(question)
    qhash = hashlib.sha256(normalized.encode()).hexdigest()
    shash = _schema_hash(schema_str)
    data_version = get_data_version()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        text("""
            DELETE FROM qa_response_cache
            WHERE query_hash = :h AND schema_hash = :s
        """),
        {"h": qhash, "s": shash},
    )

    conn.execute(
        text("""
            INSERT INTO qa_response_cache
                (query_hash, question, schema_hash, sql, response_json, answer_json, data_version, created_at)
            VALUES (:h, :q, :s, :sql, :rj, :aj, :dv, :n)
        """),
        {"h": qhash, "q": question, "s": shash, "sql": sql,
         "rj": json.dumps(response_data), "aj": json.dumps(answer),
         "dv": data_version, "n": now},
    )
    conn.commit()


def get_cached_response(question, schema_str):
    conn = get_connection()
    normalized = _normalize_question(question)
    qhash = hashlib.sha256(normalized.encode()).hexdigest()
    shash = _schema_hash(schema_str)
    current_version = get_data_version()

    row = conn.execute(
        text("""
            SELECT response_json, answer_json, sql, created_at, data_version
            FROM qa_response_cache
            WHERE query_hash = :h AND schema_hash = :s
            ORDER BY created_at DESC LIMIT 1
        """),
        {"h": qhash, "s": shash},
    ).fetchone()

    if not row:
        return None

    data_version = row[4]
    created_at = row[3]
    if isinstance(created_at, str):
        created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    created_at = created_at.replace(tzinfo=TIMEZONE)
    age = datetime.now(TIMEZONE) - created_at

    if data_version != current_version:
        return None

    if age.total_seconds() > _RESPONSE_CACHE_TTL_SECONDS:
        return None

    return {
        "response_data": json.loads(row[0]),
        "answer": json.loads(row[1]),
        "sql": row[2],
    }
