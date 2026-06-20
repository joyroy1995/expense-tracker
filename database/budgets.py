from datetime import datetime
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection, _is_postgres


OVERALL_BUDGET_CATEGORY = "__overall__"


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


def get_budget_status(user_id, month=None):
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
