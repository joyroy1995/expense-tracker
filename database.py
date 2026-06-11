from sqlalchemy import create_engine, text
from datetime import datetime
from config import DATABASE_URL, DATABASE_PATH, TIMEZONE

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        if DATABASE_URL:
            _engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
        else:
            _engine = create_engine(
                f"sqlite:///{DATABASE_PATH}", connect_args={"check_same_thread": False}
            )
    return _engine


def _is_postgres():
    return get_engine().url.drivername.startswith("postgresql")


def init_db():
    engine = get_engine()
    with engine.connect() as conn:
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
        conn.commit()


def add_expense(date, description, amount, category):
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO expenses (date, description, amount, category)
                VALUES (:date, :description, :amount, :category)
            """),
            {
                "date": date,
                "description": description,
                "amount": amount,
                "category": category,
            },
        )
        if _is_postgres():
            result = conn.execute(text("SELECT LASTVAL()"))
            expense_id = result.fetchone()[0]
        else:
            expense_id = result.lastrowid
        conn.commit()
        return expense_id


def get_expenses_by_date(date):
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT * FROM expenses WHERE date = :date ORDER BY created_at DESC"
            ),
            {"date": date},
        )
        return [dict(row._mapping) for row in result]


def get_all_expenses(limit=100):
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT * FROM expenses ORDER BY date DESC, created_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        return [dict(row._mapping) for row in result]


def get_expenses_by_month(year, month):
    engine = get_engine()
    with engine.connect() as conn:
        month_pattern = f"{year}-{month:02d}%"
        result = conn.execute(
            text(
                "SELECT * FROM expenses WHERE date LIKE :pattern ORDER BY date DESC"
            ),
            {"pattern": month_pattern},
        )
        return [dict(row._mapping) for row in result]


def get_category_totals_by_month(year, month):
    engine = get_engine()
    with engine.connect() as conn:
        month_pattern = f"{year}-{month:02d}%"
        result = conn.execute(
            text("""
                SELECT category, SUM(amount) as total, COUNT(*) as count
                FROM expenses
                WHERE date LIKE :pattern
                GROUP BY category
                ORDER BY total DESC
            """),
            {"pattern": month_pattern},
        )
        return [dict(row._mapping) for row in result]


def get_monthly_totals(months=6):
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT SUBSTR(date, 1, 7) as month, SUM(amount) as total
                FROM expenses
                GROUP BY SUBSTR(date, 1, 7)
                ORDER BY month DESC
                LIMIT :limit
            """),
            {"limit": months},
        )
        return [dict(row._mapping) for row in result]


def get_today_total():
    engine = get_engine()
    with engine.connect() as conn:
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        result = conn.execute(
            text(
                "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date = :date"
            ),
            {"date": today},
        )
        row = result.fetchone()
        return row[0] if row else 0


def get_month_total():
    engine = get_engine()
    with engine.connect() as conn:
        month_pattern = datetime.now(TIMEZONE).strftime("%Y-%m") + "%"
        result = conn.execute(
            text(
                "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date LIKE :pattern"
            ),
            {"pattern": month_pattern},
        )
        row = result.fetchone()
        return row[0] if row else 0


def get_distinct_categories():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT DISTINCT category FROM expenses ORDER BY category")
        )
        return [row[0] for row in result]


def get_distinct_years():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT DISTINCT SUBSTR(date, 1, 4) as year FROM expenses ORDER BY year")
        )
        return [int(row[0]) for row in result]


def delete_expense(expense_id):
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM expenses WHERE id = :id"), {"id": expense_id}
        )
        conn.commit()
