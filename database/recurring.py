from datetime import datetime, timedelta
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection, _is_postgres
import calendar


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
