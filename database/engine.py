from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from config import DATABASE_URL, DATABASE_PATH, TIMEZONE, enrich_db_url
from werkzeug.security import generate_password_hash
from flask import g
import flask

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
            text("CREATE INDEX IF NOT EXISTS idx_expenses_user ON expenses(user_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date)")
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

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM migrations WHERE name = 'qa_cache_features'")
        )
        if result.fetchone()[0] == 0:
            if _is_postgres():
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS qa_response_cache (
                        id SERIAL PRIMARY KEY,
                        query_hash TEXT NOT NULL,
                        question TEXT NOT NULL,
                        schema_hash TEXT NOT NULL,
                        sql TEXT NOT NULL,
                        response_json TEXT NOT NULL,
                        answer_json TEXT NOT NULL,
                        data_version INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS app_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS qa_response_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query_hash TEXT NOT NULL,
                        question TEXT NOT NULL,
                        schema_hash TEXT NOT NULL,
                        sql TEXT NOT NULL,
                        response_json TEXT NOT NULL,
                        answer_json TEXT NOT NULL,
                        data_version INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS app_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """))
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_response_cache_hash ON qa_response_cache(query_hash, schema_hash)")
            )
            if _is_postgres():
                conn.execute(
                    text("INSERT INTO app_metadata (key, value) VALUES ('data_version', '1') ON CONFLICT (key) DO NOTHING")
                )
            else:
                conn.execute(
                    text("INSERT OR IGNORE INTO app_metadata (key, value) VALUES ('data_version', '1')")
                )
            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                text("INSERT INTO migrations (name, applied_at) VALUES ('qa_cache_features', :n)"),
                {"n": now},
            )
            conn.commit()


def get_data_version():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM app_metadata WHERE key = 'data_version'")
            ).fetchone()
            return int(row[0]) if row else 1
    except Exception:
        return 1


def bump_data_version():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE app_metadata SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = 'data_version'")
            )
            conn.commit()
    except Exception:
        pass


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
