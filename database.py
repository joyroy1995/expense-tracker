from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from config import DATABASE_URL, DATABASE_PATH, TIMEZONE, enrich_db_url
from werkzeug.security import generate_password_hash
from flask import g
import flask
import secrets
import hashlib
import re

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
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS budgets (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, category)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS recurring_transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                frequency TEXT NOT NULL DEFAULT 'monthly',
                interval_value INTEGER DEFAULT 1,
                interval_unit TEXT,
                next_date TEXT NOT NULL,
                end_date TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, category),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        )
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS recurring_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                frequency TEXT NOT NULL DEFAULT 'monthly',
                interval_value INTEGER DEFAULT 1,
                interval_unit TEXT,
                next_date TEXT NOT NULL,
                end_date TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
    if _is_postgres():
        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS qa_cache (
                    id SERIAL PRIMARY KEY,
                    query_hash TEXT NOT NULL,
                    normalized_query TEXT NOT NULL,
                    sql TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    last_used_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    hit_count INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_qa_cache_hash ON qa_cache(query_hash)")
        )
        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    endpoint TEXT NOT NULL,
                    p256dh_key TEXT NOT NULL,
                    auth_key TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, endpoint)
                )
            """)
        )
    else:
        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS qa_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT NOT NULL,
                    normalized_query TEXT NOT NULL,
                    sql TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    last_used_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    hit_count INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_qa_cache_hash ON qa_cache(query_hash)")
        )
        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    endpoint TEXT NOT NULL,
                    p256dh_key TEXT NOT NULL,
                    auth_key TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, endpoint)
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

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM migrations WHERE name = 'budgets_table'")
        )
        if result.fetchone()[0] == 0:
            if _is_postgres():
                conn.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS budgets (
                            id SERIAL PRIMARY KEY,
                            user_id INTEGER NOT NULL REFERENCES users(id),
                            category TEXT NOT NULL,
                            amount REAL NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(user_id, category)
                        )
                    """)
                )
            else:
                conn.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS budgets (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            category TEXT NOT NULL,
                            amount REAL NOT NULL,
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(user_id, category),
                            FOREIGN KEY (user_id) REFERENCES users(id)
                        )
                    """)
                )
            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                text("INSERT INTO migrations (name, applied_at) VALUES ('budgets_table', :n)"),
                {"n": now},
            )
            conn.commit()

    # ── Migration: recurring_transactions table ──
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM migrations WHERE name = 'recurring_transactions'")
        )
        if result.fetchone()[0] == 0:
            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                text("INSERT INTO migrations (name, applied_at) VALUES ('recurring_transactions', :n)"),
                {"n": now},
            )
            conn.commit()

    # ── Migration: push_subscriptions table ──
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM migrations WHERE name = 'push_subscriptions'")
        )
        if result.fetchone()[0] == 0:
            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                text("INSERT INTO migrations (name, applied_at) VALUES ('push_subscriptions', :n)"),
                {"n": now},
            )
            conn.commit()

    # ── Migration: last_digest_sent column ──
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM migrations WHERE name = 'last_digest_sent'")
        )
        if result.fetchone()[0] == 0:
            if _is_postgres():
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN last_digest_sent DATE")
                )
            else:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN last_digest_sent TEXT")
                )
            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                text("INSERT INTO migrations (name, applied_at) VALUES ('last_digest_sent', :n)"),
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


def get_daily_totals(year, month, user_id=None):
    """Return daily totals for a given month. Returns [{date, total}, ...]."""
    conn = get_connection()
    month_pattern = f"{year}-{month:02d}%"
    uf = _user_filter(user_id)
    params = {"pattern": month_pattern}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(f"SELECT date, COALESCE(SUM(amount), 0) as total FROM expenses WHERE date LIKE :pattern{uf} GROUP BY date ORDER BY date"),
        params,
    )
    return [dict(row._mapping) for row in result]


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


def get_week_total(user_id, start_date, end_date):
    """Total spending between two dates (inclusive)."""
    conn = get_connection()
    uf = _user_filter(user_id)
    params = {"start": start_date, "end": end_date}
    params.update(_user_params(user_id))
    result = conn.execute(
        text(
            f"SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= :start AND date <= :end{uf}"
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


# ── Push subscriptions ──────────────────────────────────────

def save_push_subscription(user_id, endpoint, p256dh_key, auth_key):
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        text("""
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh_key, auth_key, created_at)
            VALUES (:uid, :ep, :p256, :auth, :now)
            ON CONFLICT(user_id, endpoint) DO UPDATE SET
                p256dh_key = :p2562, auth_key = :auth2, created_at = :now2
        """),
        {"uid": user_id, "ep": endpoint, "p256": p256dh_key, "auth": auth_key, "now": now,
         "p2562": p256dh_key, "auth2": auth_key, "now2": now},
    )
    conn.commit()


def remove_push_subscription(user_id, endpoint):
    conn = get_connection()
    conn.execute(
        text("DELETE FROM push_subscriptions WHERE user_id = :uid AND endpoint = :ep"),
        {"uid": user_id, "ep": endpoint},
    )
    conn.commit()


def get_user_push_subscriptions(user_id):
    conn = get_connection()
    rows = conn.execute(
        text("SELECT endpoint, p256dh_key, auth_key FROM push_subscriptions WHERE user_id = :uid"),
        {"uid": user_id},
    ).fetchall()
    return [{"endpoint": r[0], "p256dh_key": r[1], "auth_key": r[2]} for r in rows]


def get_all_push_subscriptions():
    conn = get_connection()
    rows = conn.execute(
        text("SELECT DISTINCT user_id, endpoint, p256dh_key, auth_key FROM push_subscriptions")
    ).fetchall()
    return [{"user_id": r[0], "endpoint": r[1], "p256dh_key": r[2], "auth_key": r[3]} for r in rows]


# ── Digest helpers ──────────────────────────────────────────────

def get_user_last_digest_sent(user_id):
    conn = get_connection()
    row = conn.execute(
        text("SELECT last_digest_sent FROM users WHERE id = :id"),
        {"id": user_id},
    ).fetchone()
    return row[0] if row else None


def set_user_last_digest_sent(user_id, date_str):
    conn = get_connection()
    conn.execute(
        text("UPDATE users SET last_digest_sent = :d WHERE id = :id"),
        {"d": date_str, "id": user_id},
    )
    conn.commit()


def get_yesterday_expense_summary(user_id, yesterday):
    conn = get_connection()
    row = conn.execute(
        text("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM expenses WHERE user_id = :uid AND date = :d"),
        {"uid": user_id, "d": yesterday},
    ).fetchone()
    total = row[0] if row else 0
    count = row[1] if row else 0
    row = conn.execute(
        text("""
            SELECT category, COALESCE(SUM(amount), 0) as cat_total
            FROM expenses WHERE user_id = :uid AND date = :d
            GROUP BY category ORDER BY cat_total DESC LIMIT 1
        """),
        {"uid": user_id, "d": yesterday},
    ).fetchone()
    top_category = row[0] if row else None
    top_cat_amount = row[1] if row else 0
    row = conn.execute(
        text("""
            SELECT description, amount FROM expenses
            WHERE user_id = :uid AND date = :d
            ORDER BY amount DESC LIMIT 1
        """),
        {"uid": user_id, "d": yesterday},
    ).fetchone()
    top_exp_desc = row[0] if row else None
    top_exp_amount = row[1] if row else 0
    return {
        "total": total,
        "count": count,
        "top_category": top_category,
        "top_category_amount": top_cat_amount,
        "top_expense": top_exp_desc,
        "top_expense_amount": top_exp_amount,
    }


def get_month_to_date_total(user_id, month):
    conn = get_connection()
    row = conn.execute(
        text("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND SUBSTR(date, 1, 7) = :m"),
        {"uid": user_id, "m": month},
    ).fetchone()
    return row[0] if row else 0


def get_daily_average(user_id, month):
    conn = get_connection()
    row = conn.execute(
        text("""
            SELECT COALESCE(AVG(daily_total), 0) FROM (
                SELECT SUM(amount) as daily_total
                FROM expenses WHERE user_id = :uid AND SUBSTR(date, 1, 7) = :m
                GROUP BY date
            )
        """),
        {"uid": user_id, "m": month},
    ).fetchone()
    return row[0] if row else 0


OVERALL_BUDGET_CATEGORY = "__overall__"


# ── Budget CRUD ──────────────────────────────────────────────

def set_budget(user_id, category, amount):
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    if _is_postgres():
        conn.execute(
            text("""
                INSERT INTO budgets (user_id, category, amount, created_at, updated_at)
                VALUES (:uid, :cat, :amt, :now, :now)
                ON CONFLICT(user_id, category) DO UPDATE SET amount = :amt2, updated_at = :now2
            """),
            {"uid": user_id, "cat": category, "amt": amount, "now": now,
             "amt2": amount, "now2": now},
        )
    else:
        conn.execute(
            text("""
                INSERT INTO budgets (user_id, category, amount, created_at, updated_at)
                VALUES (:uid, :cat, :amt, :now, :now)
                ON CONFLICT(user_id, category) DO UPDATE SET amount = :amt2, updated_at = :now2
            """),
            {"uid": user_id, "cat": category, "amt": amount, "now": now,
             "amt2": amount, "now2": now},
        )
    conn.commit()


def get_budgets(user_id):
    conn = get_connection()
    rows = conn.execute(
        text("SELECT id, category, amount, created_at, updated_at FROM budgets WHERE user_id = :uid ORDER BY category"),
        {"uid": user_id},
    ).fetchall()
    return [dict(row._mapping) for row in rows]


def delete_budget(budget_id):
    conn = get_connection()
    conn.execute(text("DELETE FROM budgets WHERE id = :id"), {"id": budget_id})
    conn.commit()


# ── Recurring Transactions CRUD ────────────────────────────────

def add_recurring(user_id, description, amount, category, frequency, next_date, end_date=None, interval_value=1, interval_unit=None):
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    result = conn.execute(
        text("""
            INSERT INTO recurring_transactions
                (user_id, description, amount, category, frequency, interval_value, interval_unit, next_date, end_date, created_at, updated_at)
            VALUES (:uid, :desc, :amt, :cat, :freq, :iv, :iu, :nd, :ed, :n, :n)
        """),
        {"uid": user_id, "desc": description, "amt": amount, "cat": category,
         "freq": frequency, "iv": interval_value, "iu": interval_unit,
         "nd": next_date, "ed": end_date, "n": now},
    )
    conn.commit()
    if _is_postgres():
        result = conn.execute(text("SELECT LASTVAL()"))
        return result.fetchone()[0]
    return result.lastrowid


def get_recurring_transactions(user_id):
    conn = get_connection()
    rows = conn.execute(
        text("""
            SELECT id, description, amount, category, frequency, interval_value, interval_unit,
                   next_date, end_date, is_active, created_at, updated_at
            FROM recurring_transactions
            WHERE user_id = :uid
            ORDER BY next_date ASC
        """),
        {"uid": user_id},
    ).fetchall()
    return [dict(row._mapping) for row in rows]


def get_recurring_by_id(recurring_id):
    conn = get_connection()
    row = conn.execute(
        text("SELECT * FROM recurring_transactions WHERE id = :id"),
        {"id": recurring_id},
    ).fetchone()
    return dict(row._mapping) if row else None


def update_recurring(recurring_id, **kwargs):
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    allowed = {"description", "amount", "category", "frequency", "interval_value", "interval_unit", "next_date", "end_date", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False
    updates["id"] = recurring_id
    updates["n"] = now
    set_clause = ", ".join(f"{k} = :{k}" for k in updates if k != "id" and k != "n")
    set_clause += ", updated_at = :n"
    conn.execute(
        text(f"UPDATE recurring_transactions SET {set_clause} WHERE id = :id"),
        updates,
    )
    conn.commit()
    return True


def delete_recurring(recurring_id):
    conn = get_connection()
    conn.execute(text("DELETE FROM recurring_transactions WHERE id = :id"), {"id": recurring_id})
    conn.commit()


def get_due_recurring(user_id, as_of_date=None):
    if as_of_date is None:
        as_of_date = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    conn = get_connection()
    rows = conn.execute(
        text("""
            SELECT * FROM recurring_transactions
            WHERE user_id = :uid AND is_active = 1 AND next_date <= :ad
            AND (end_date IS NULL OR end_date >= :ad2)
            ORDER BY next_date ASC
        """),
        {"uid": user_id, "ad": as_of_date, "ad2": as_of_date},
    ).fetchall()
    return [dict(row._mapping) for row in rows]


def update_next_date(recurring_id, next_date):
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        text("UPDATE recurring_transactions SET next_date = :nd, updated_at = :n WHERE id = :id"),
        {"nd": next_date, "n": now, "id": recurring_id},
    )
    conn.commit()


def compute_next_date(current_next_date, frequency, interval_value=1, interval_unit=None):
    from datetime import timedelta
    import calendar
    d = datetime.strptime(current_next_date, "%Y-%m-%d").date()
    freq = frequency.lower()
    unit = (interval_unit or freq).lower()
    if unit == "daily" or unit == "days":
        return (d + timedelta(days=interval_value)).isoformat()
    elif unit == "weekly" or unit == "weeks":
        return (d + timedelta(weeks=interval_value)).isoformat()
    elif unit == "monthly" or unit == "months":
        month = d.month + interval_value
        year = d.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        last_day = calendar.monthrange(year, month)[1]
        day = min(d.day, last_day)
        return f"{year:04d}-{month:02d}-{day:02d}"
    elif unit == "yearly" or unit == "years":
        year = d.year + interval_value
        last_day = calendar.monthrange(year, d.month)[1]
        day = min(d.day, last_day)
        return f"{year:04d}-{d.month:02d}-{day:02d}"
    return current_next_date


def get_budget_status(user_id, month=None):
    """Return per-category budget vs actual for a given month (YYYY-MM).
    Returns list of dicts: {category, budget_amount, spent, percentage} for
    all budgets (including __overall__). __overall__ spent = total across ALL categories.
    """
    if month is None:
        now = datetime.now(TIMEZONE)
        month = now.strftime("%Y-%m")
    conn = get_connection()
    rows = conn.execute(
        text("""
            SELECT b.category, b.amount as budget_amount,
                   COALESCE(SUM(e.amount), 0) as spent
            FROM budgets b
            LEFT JOIN expenses e
                ON e.user_id = b.user_id
                AND e.category = b.category
                AND SUBSTR(e.date, 1, 7) = :month
            WHERE b.user_id = :uid
            GROUP BY b.id, b.category, b.amount
            ORDER BY b.category
        """),
        {"uid": user_id, "month": month},
    ).fetchall()
    result = []
    # Pre-compute total spending once
    total_spent = None
    for row in rows:
        r = dict(row._mapping)
        if r["category"] == OVERALL_BUDGET_CATEGORY:
            if total_spent is None:
                total_row = conn.execute(
                    text("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND SUBSTR(date, 1, 7) = :month"),
                    {"uid": user_id, "month": month},
                ).fetchone()
                total_spent = total_row[0]
            r["spent"] = total_spent
        r["percentage"] = round((r["spent"] / r["budget_amount"]) * 100, 1) if r["budget_amount"] > 0 else 0
        result.append(r)
    return result


# ── NL Q&A Schema ────────────────────────────────────────────

_ALL_CATEGORIES = [
    "Bills", "Dining Out", "Education", "Entertainment", "Food",
    "Fruits", "Gifts", "Groceries", "Health", "Investment",
    "Other", "Personal Care", "Rent", "Savings", "Shopping",
    "Transport", "Travel",
]

SCHEMA_VERSION = 3


def get_schema():
    """Return a human-readable DB schema string for the LLM."""
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

    # Get date range of expenses
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


# ── NL Q&A Semantic Caching ─────────────────────────────────

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


def _normalize_question(q):
    """Normalize a question for fuzzy cache matching."""
    q = q.lower()
    q = re.sub(r'[^\w\s]', ' ', q)
    q = re.sub(r'\s+', ' ', q).strip()
    tokens = [w for w in q.split() if w not in _STOP_WORDS and len(w) > 1]
    return ' '.join(sorted(set(tokens)))


def _schema_hash(schema_str):
    """Return a stable hash of the schema string to detect schema changes."""
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]


def cache_qa_sql(question, sql, schema_str):
    """Store a generated SQL query in the cache."""
    conn = get_connection()
    normalized = _normalize_question(question)
    qhash = hashlib.sha256(normalized.encode()).hexdigest()
    shash = _schema_hash(schema_str)
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    # Check if exists
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


_FUZZY_THRESHOLD = 0.75


def _token_jaccard(a, b):
    """Jaccard similarity of token sets."""
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
    """Look up a cached SQL query by semantic similarity. Returns dict or None."""
    conn = get_connection()
    normalized = _normalize_question(question)
    qhash = hashlib.sha256(normalized.encode()).hexdigest()
    shash = _schema_hash(schema_str)

    # 1. Try exact hash match (fast path)
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

    # 2. Try token-subset / Jaccard fuzzy match
    rows = conn.execute(
        text("SELECT normalized_query, sql FROM qa_cache WHERE schema_hash = :s"),
        {"s": shash},
    ).fetchall()

    norm_tokens = set(normalized.split())
    best_sql = None
    best_score = 0.0

    for r in rows:
        cached_tokens = set(r[0].split())
        # Subset check: one is fully contained in the other
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
