import hashlib
import re
from datetime import datetime
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection


_ALL_CATEGORIES = [
    "Bills", "Dining Out", "Education", "Entertainment", "Food",
    "Fruits", "Gifts", "Groceries", "Health", "Investment",
    "Other", "Personal Care", "Rent", "Savings", "Shopping",
    "Transport", "Travel",
]

SCHEMA_VERSION = 3

OVERALL_BUDGET_CATEGORY = "__overall__"

_STOP_WORDS = frozenset({
    "me", "my", "the", "a", "an", "did", "do", "does", "is", "are",
    "was", "were", "of", "in", "on", "at", "to", "for", "with",
    "how", "what", "why", "show", "tell", "list", "give", "which",
    "when", "where", "who", "all", "total", "spending", "expenses",
    "much", "many", "please", "can", "could", "would", "will",
    "am", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "but", "or", "if", "so", "up", "down", "out", "just",
    "about", "than", "too", "also", "very", "some", "any", "every",
})

_FUZZY_THRESHOLD = 0.75


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


def _normalize_question(q):
    q = q.lower()
    q = re.sub(r'[^\w\s]', ' ', q)
    q = re.sub(r'\s+', ' ', q).strip()
    tokens = [w for w in q.split() if w not in _STOP_WORDS and len(w) > 1]
    return ' '.join(sorted(set(tokens)))


def _schema_hash(schema_str):
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]


def cache_qa_sql(question, sql, schema_str):
    conn = get_connection()
    normalized = _normalize_question(question)
    qhash = hashlib.sha256(normalized.encode()).hexdigest()
    shash = _schema_hash(schema_str)
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    existing = conn.execute(
        text("SELECT id, hit_count FROM qa_cache WHERE query_hash = :h AND schema_hash = :s"),
        {"h": qhash, "s": shash},
    ).fetchone()

    if existing:
        conn.execute(
            text("UPDATE qa_cache SET last_used_at = :n, hit_count = hit_count + 1 WHERE id = :id"),
            {"n": now, "id": existing[0]},
        )
    else:
        conn.execute(
            text("""
                INSERT INTO qa_cache (query_hash, normalized_query, sql, schema_hash, last_used_at, created_at)
                VALUES (:h, :nq, :sql, :sh, :n, :n)
            """),
            {"h": qhash, "nq": normalized, "sql": sql, "sh": shash, "n": now},
        )
    conn.commit()


def _token_jaccard(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    intersection = sa & sb
    if not intersection:
        return 0.0
    return len(intersection) / len(sa | sb)


def get_cached_sql(question, schema_str):
    conn = get_connection()
    normalized = _normalize_question(question)
    qhash = hashlib.sha256(normalized.encode()).hexdigest()
    shash = _schema_hash(schema_str)

    row = conn.execute(
        text("""
            SELECT sql FROM qa_cache
            WHERE query_hash = :h AND schema_hash = :s
            ORDER BY last_used_at DESC LIMIT 1
        """),
        {"h": qhash, "s": shash},
    ).fetchone()
    if row:
        return {"sql": row[0], "hit": True}

    rows = conn.execute(
        text("SELECT normalized_query, sql FROM qa_cache WHERE schema_hash = :s"),
        {"s": shash},
    ).fetchall()

    norm_tokens = set(normalized.split())
    best_sql = None
    best_score = 0.0

    for r in rows:
        cached_tokens = set(r[0].split())
        if norm_tokens and cached_tokens and (norm_tokens <= cached_tokens or cached_tokens <= norm_tokens):
            score = len(norm_tokens & cached_tokens) / min(len(norm_tokens), len(cached_tokens))
        else:
            score = _token_jaccard(normalized, r[0])
        if score > best_score:
            best_score = score
            best_sql = r[1]

    if best_score >= _FUZZY_THRESHOLD and best_sql:
        return {"sql": best_sql, "hit": False}
    return None
