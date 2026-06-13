from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from config import DATABASE_URL, DATABASE_PATH, TIMEZONE, enrich_db_url
from werkzeug.security import generate_password_hash
from flask import g
import flask
import secrets

_engine = None
_db_init_done = False


def get_engine():
    global _engine
    if _engine is None:
        url = enrich_db_url(DATABASE_URL)
        if url:
            _engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=1,
                max_overflow=2,
                pool_recycle=60,
            )
        else:
            _engine = create_engine(
                f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False}
            )
    return _engine


def _ensure_init():
    global _db_init_done
    if _db_init_done:
        return
    _db_init_done = True
    engine = get_engine()
    with engine.connect() as conn:
        _init_schema(conn)
        conn.commit()
    _run_migrations()
    _seed_superuser()


def _init_schema(conn):
    if _is_postgres():
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)"
            )
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        result = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'expenses' AND column_name = 'user_id'")
        )
        if not result.fetchone():
            conn.execute(
                text("ALTER TABLE expenses ADD COLUMN user_id INTEGER DEFAULT 1")
            )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_expenses_user ON expenses(user_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date)")
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS learned_categories (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                keyword TEXT NOT NULL,
                category TEXT NOT NULL,
                learned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, keyword)
            )
        """)
        )
    else:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category)"
            )
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        )
        result = conn.execute(text("PRAGMA table_info(expenses)"))
        cols = [r[1] for r in result]
        if "user_id" not in cols:
            conn.execute(
                text("ALTER TABLE expenses ADD COLUMN user_id INTEGER DEFAULT 1")
            )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_expenses_user ON expenses(user_id)")  # sqlite
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date)")  # sqlite
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS learned_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                keyword TEXT NOT NULL,
                category TEXT NOT NULL,
                learned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, keyword),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        )
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    )


def get_connection():
    _ensure_init()
    if flask.has_request_context():
        if "db_conn" not in g:
            g.db_conn = get_engine().connect()
        return g.db_conn
    return get_engine().connect()


def close_connection(exception=None):
    """Close the request-scoped database connection (called by teardown_appcontext)."""
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()


def _is_postgres():
    return get_engine().url.drivername.startswith("postgresql")


def _run_migrations():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM migrations WHERE name = 'utc_to_dhaka'")
        )
        if result.fetchone()[0] == 0:
            if _is_postgres():
                conn.execute(
                    text("UPDATE expenses SET created_at = created_at + INTERVAL '6 hours' WHERE created_at IS NOT NULL")
                )
                conn.execute(
                    text("UPDATE users SET created_at = created_at + INTERVAL '6 hours' WHERE created_at IS NOT NULL")
                )
            else:
                conn.execute(
                    text("UPDATE expenses SET created_at = datetime(created_at, '+6 hours') WHERE created_at IS NOT NULL")
                )
                conn.execute(
                    text("UPDATE users SET created_at = datetime(created_at, '+6 hours') WHERE created_at IS NOT NULL")
                )
            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                text("INSERT INTO migrations (name, applied_at) VALUES ('utc_to_dhaka', :n)"),
                {"n": now},
            )
            conn.commit()


def _seed_superuser():
    from config import USERNAME, PASSWORD

    if not USERNAME or not PASSWORD:
        return
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM users"))
        if result.fetchone()[0] == 0:
            pw_hash = generate_password_hash(PASSWORD)
            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (:u, :p, 'superuser', :c)"
                ),
                {"u": USERNAME, "p": pw_hash, "c": now},
            )
            conn.commit()


# ── User functions ──────────────────────────────────────────

def create_user(username, password_hash, role="user"):
    conn = get_connection()
    result = conn.execute(text("SELECT COUNT(*) FROM users"))
    count = result.fetchone()[0]
    if count == 0:
        role = "superuser"
    try:
        now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (:u, :p, :r, :c)"
            ),
            {"u": username, "p": password_hash, "r": role, "c": now},
        )
        conn.commit()
        if _is_postgres():
            result = conn.execute(text("SELECT LASTVAL()"))
            return result.fetchone()[0]
        return result.lastrowid
    except Exception:
        return None


def get_user_by_username(username):
    conn = get_connection()
    result = conn.execute(
        text("SELECT * FROM users WHERE username = :u"), {"u": username}
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


def get_user_by_id(user_id):
    conn = get_connection()
    result = conn.execute(
        text("SELECT * FROM users WHERE id = :id"), {"id": user_id}
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


def get_all_users():
    conn = get_connection()
    result = conn.execute(
        text("""
            SELECT u.*, COUNT(e.id) as expense_count
            FROM users u
            LEFT JOIN expenses e ON e.user_id = u.id
            GROUP BY u.id
            ORDER BY u.created_at DESC
        """)
    )
    return [dict(row._mapping) for row in result]


def update_user_role(user_id, new_role):
    conn = get_connection()
    conn.execute(
        text("UPDATE users SET role = :r WHERE id = :id"),
        {"r": new_role, "id": user_id},
    )
    conn.commit()


def delete_user(user_id):
    conn = get_connection()
    conn.execute(text("DELETE FROM expenses WHERE user_id = :id"), {"id": user_id})
    conn.execute(text("DELETE FROM password_resets WHERE user_id = :id"), {"id": user_id})
    conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    conn.commit()


def get_user_expense_stats(user_id):
    conn = get_connection()
    user = conn.execute(
        text("SELECT username, role, created_at FROM users WHERE id = :id"),
        {"id": user_id},
    ).fetchone()
    if not user:
        return None
    result = conn.execute(
        text("""
            SELECT COUNT(*) as total_count, COALESCE(SUM(amount), 0) as total_amount
            FROM expenses WHERE user_id = :id
        """),
        {"id": user_id},
    ).fetchone()
    stats = dict(result._mapping)
    stats["username"] = user[0]
    stats["role"] = user[1]
    stats["member_since"] = user[2]
    return stats


# ── Password reset functions ────────────────────────────────

def create_reset_token(user_id):
    conn = get_connection()
    token = secrets.token_urlsafe(32)
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (datetime.now(TIMEZONE) + timedelta(hours=1)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn.execute(
        text(
            "INSERT INTO password_resets (user_id, token, expires_at, created_at) VALUES (:uid, :tok, :exp, :c)"
        ),
        {"uid": user_id, "tok": token, "exp": expires_at, "c": now},
    )
    conn.commit()
    return token


def validate_reset_token(token):
    conn = get_connection()
    now_dhaka = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    result = conn.execute(
        text("""
            SELECT * FROM password_resets
            WHERE token = :tok AND used = 0
        """),
        {"tok": token},
    )
    row = result.fetchone()
    if not row:
        return None
    r = dict(row._mapping)
    if r["expires_at"] <= now_dhaka:
        return None
    return r


def use_reset_token(token, password_hash):
    conn = get_connection()
    now_dhaka = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    record = conn.execute(
        text(
            "SELECT * FROM password_resets WHERE token = :tok AND used = 0"
        ),
        {"tok": token},
    ).fetchone()
    if not record:
        return False
    record = dict(record._mapping)
    if record["expires_at"] <= now_dhaka:
        return False
    conn.execute(
        text("UPDATE users SET password_hash = :p WHERE id = :id"),
        {"p": password_hash, "id": record["user_id"]},
    )
    conn.execute(
        text("UPDATE password_resets SET used = 1 WHERE token = :tok"),
        {"tok": token},
    )
    conn.commit()
    return True


# ── Expense query helpers ───────────────────────────────────

def _user_filter(user_id):
    if user_id is not None:
        return " AND user_id = :user_id"
    return ""


def _user_params(user_id):
    if user_id is not None:
        return {"user_id": user_id}
    return {}


# ── Expense functions (modified with optional user_id) ──────

def add_expense(date, description, amount, category, user_id=1):
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    result = conn.execute(
        text("""
            INSERT INTO expenses (date, description, amount, category, user_id, created_at)
            VALUES (:date, :description, :amount, :category, :user_id, :created_at)
        """),
        {
            "date": date,
            "description": description,
            "amount": amount,
            "category": category,
            "user_id": user_id,
            "created_at": now,
        },
    )
    if _is_postgres():
        result = conn.execute(text("SELECT LASTVAL()"))
        expense_id = result.fetchone()[0]
    else:
        expense_id = result.lastrowid
    conn.commit()
    return expense_id


def get_expenses_by_date(date, user_id=None):
    conn = get_connection()
    uf = _user_filter(user_id)
    params = {"date": date}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(f"SELECT * FROM expenses WHERE date = :date{uf} ORDER BY created_at DESC"),
        params,
    )
    return [dict(row._mapping) for row in result]


def get_all_expenses(limit=100, user_id=None):
    conn = get_connection()
    uf = _user_filter(user_id)
    params = {"limit": limit}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(
            f"SELECT * FROM expenses ORDER BY date DESC, created_at DESC LIMIT :limit"
        ),
        params,
    )
    return [dict(row._mapping) for row in result]


def get_recent_expenses_paginated(page=1, per_page=20, user_id=None, since=None):
    conn = get_connection()
    offset = (page - 1) * per_page
    conditions = []
    params = {}

    if since:
        conditions.append("date >= :since")
        params["since"] = since
    if user_id is not None:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

    count_result = conn.execute(
        text(f"SELECT COUNT(*) FROM expenses{where_clause}"),
        params,
    )
    total = count_result.fetchone()[0]

    result = conn.execute(
        text(
            f"SELECT * FROM expenses{where_clause} ORDER BY date DESC, created_at DESC LIMIT :lim OFFSET :off"
        ),
        {**params, "lim": per_page, "off": offset},
    )
    expenses = [dict(row._mapping) for row in result]

    return {
        "expenses": expenses,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


def get_expenses_by_month(year, month, user_id=None):
    conn = get_connection()
    month_pattern = f"{year}-{month:02d}%"
    uf = _user_filter(user_id)
    params = {"pattern": month_pattern}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(
            f"SELECT * FROM expenses WHERE date LIKE :pattern{uf} ORDER BY date DESC"
        ),
        params,
    )
    return [dict(row._mapping) for row in result]


def get_expenses_filtered(year, month, user_id=None, search=None, page=1, per_page=20):
    conn = get_connection()
    offset = (page - 1) * per_page
    month_pattern = f"{year}-{month:02d}%"
    conditions = ["date LIKE :pattern"]
    params = {"pattern": month_pattern}

    if user_id is not None:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id

    if search:
        conditions.append("description LIKE :search")
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions)

    count_result = conn.execute(
        text(f"SELECT COUNT(*) FROM expenses WHERE {where_clause}"),
        params,
    )
    total = count_result.fetchone()[0]

    result = conn.execute(
        text(
            f"SELECT * FROM expenses WHERE {where_clause} ORDER BY date DESC, created_at DESC LIMIT :lim OFFSET :off"
        ),
        {**params, "lim": per_page, "off": offset},
    )
    expenses = [dict(row._mapping) for row in result]

    return {
        "expenses": expenses,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


def get_expenses_export(year, month, user_id=None, search=None):
    conn = get_connection()
    month_pattern = f"{year}-{month:02d}%"
    conditions = ["date LIKE :pattern"]
    params = {"pattern": month_pattern}

    if user_id is not None:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id

    if search:
        conditions.append("description LIKE :search")
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions)
    result = conn.execute(
        text(
            f"SELECT * FROM expenses WHERE {where_clause} ORDER BY date ASC, created_at ASC"
        ),
        params,
    )
    return [dict(row._mapping) for row in result]


def get_expenses_by_category_month(year, month, category, user_id=None, page=1, per_page=20):
    conn = get_connection()
    month_pattern = f"{year}-{month:02d}%"
    conditions = ["date LIKE :pattern", "category = :category"]
    params = {"pattern": month_pattern, "category": category}
    if user_id is not None:
        conditions.append("user_id = :user_id")
        params["user_id"] = user_id
    where_clause = " AND ".join(conditions)

    count_result = conn.execute(
        text(f"SELECT COUNT(*) FROM expenses WHERE {where_clause}"), params
    )
    total = count_result.fetchone()[0]

    offset = (page - 1) * per_page
    result = conn.execute(
        text(f"SELECT * FROM expenses WHERE {where_clause} ORDER BY date ASC, created_at ASC LIMIT :lim OFFSET :off"),
        {**params, "lim": per_page, "off": offset},
    )
    expenses = [dict(row._mapping) for row in result]

    return {
        "expenses": expenses,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


def get_category_totals_by_month(year, month, user_id=None):
    conn = get_connection()
    month_pattern = f"{year}-{month:02d}%"
    uf = _user_filter(user_id)
    params = {"pattern": month_pattern}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(f"""
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE date LIKE :pattern{uf}
            GROUP BY category
            ORDER BY total DESC
        """),
        params,
    )
    return [dict(row._mapping) for row in result]


def get_monthly_totals(months=6, user_id=None):
    conn = get_connection()
    uf = _user_filter(user_id)
    params = {"limit": months}
    params.update(_user_params(user_id))

    if _is_postgres():
        result = conn.execute(
            text(f"""
                SELECT SUBSTR(date::text, 1, 7) as month, SUM(amount) as total
                FROM expenses
                WHERE 1=1{uf}
                GROUP BY SUBSTR(date::text, 1, 7)
                ORDER BY month DESC
                LIMIT :limit
            """),
            params,
        )
    else:
        result = conn.execute(
            text(f"""
                SELECT SUBSTR(date, 1, 7) as month, SUM(amount) as total
                FROM expenses
                WHERE 1=1{uf}
                GROUP BY SUBSTR(date, 1, 7)
                ORDER BY month DESC
                LIMIT :limit
            """),
            params,
        )
    return [dict(row._mapping) for row in result]


def get_today_total(user_id=None):
    conn = get_connection()
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    uf = _user_filter(user_id)
    params = {"date": today}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(
            f"SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date = :date{uf}"
        ),
        params,
    )
    row = result.fetchone()
    return row[0] if row else 0


def get_month_total(user_id=None):
    conn = get_connection()
    month_pattern = datetime.now(TIMEZONE).strftime("%Y-%m") + "%"
    uf = _user_filter(user_id)
    params = {"pattern": month_pattern}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(
            f"SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date LIKE :pattern{uf}"
        ),
        params,
    )
    row = result.fetchone()
    return row[0] if row else 0


def get_distinct_categories():
    conn = get_connection()
    result = conn.execute(
        text("SELECT DISTINCT category FROM expenses ORDER BY category")
    )
    return [row[0] for row in result]


def get_distinct_years(user_id=None):
    conn = get_connection()
    uf = _user_filter(user_id)
    params = {}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(f"SELECT DISTINCT SUBSTR(date, 1, 4) as year FROM expenses WHERE 1=1{uf} ORDER BY year"),
        params,
    )
    return [int(row[0]) for row in result]


def delete_expense(expense_id):
    conn = get_connection()
    conn.execute(
        text("DELETE FROM expenses WHERE id = :id"), {"id": expense_id}
    )
    conn.commit()


# ── Learned categories ────────────────────────────────────────

def learn_category(user_id, keyword, category):
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        text("""
            INSERT INTO learned_categories (user_id, keyword, category, learned_at)
            VALUES (:uid, :kw, :cat, :now)
            ON CONFLICT(user_id, keyword) DO UPDATE SET category = :cat2, learned_at = :now2
        """),
        {"uid": user_id, "kw": keyword, "cat": category, "now": now,
         "cat2": category, "now2": now},
    )
    conn.commit()


def get_learned_categories(user_id):
    conn = get_connection()
    rows = conn.execute(
        text("""
            SELECT keyword, category FROM learned_categories
            WHERE user_id = :uid OR user_id IS NULL
        """),
        {"uid": user_id},
    ).fetchall()
    return {row[0]: row[1] for row in rows}


# ── NL Q&A Schema ────────────────────────────────────────────

def get_schema():
    """Return a human-readable DB schema string for the LLM."""
    conn = get_connection()
    cats = conn.execute(
        text("SELECT DISTINCT category FROM expenses ORDER BY category")
    ).fetchall()
    categories = [r[0] for r in cats]
    cats_str = ", ".join(categories) if categories else "Groceries, Transport, Dining Out, etc."

    return f"""
Table: expenses
Columns:
- id (INTEGER): primary key
- date (TEXT): YYYY-MM-DD format
- description (TEXT): expense description in Banglish/Bengali/English
- amount (REAL): amount in BDT
- category (TEXT): known categories: {cats_str}
- user_id (INTEGER): owner of the expense
- created_at (TEXT): timestamp when recorded

Table: users
Columns:
- id (INTEGER): primary key
- username (TEXT)
- role (TEXT): 'user' or 'superuser'
- created_at (TEXT): timestamp
"""
