from datetime import datetime
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection, _is_postgres, bump_data_version


def _user_filter(user_id):
    if user_id is not None:
        return " AND user_id = :user_id"
    return ""


def _user_params(user_id):
    if user_id is not None:
        return {"user_id": user_id}
    return {}


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
    bump_data_version()
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


def update_expense(expense_id, **kwargs):
    allowed = {"date", "description", "amount", "category"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False
    conn = get_connection()
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = expense_id
    conn.execute(
        text(f"UPDATE expenses SET {set_clause} WHERE id = :id"),
        updates,
    )
    conn.commit()
    bump_data_version()
    return True


def get_expense_by_id(expense_id):
    conn = get_connection()
    result = conn.execute(
        text("SELECT * FROM expenses WHERE id = :id"), {"id": expense_id}
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


def delete_expense(expense_id):
    conn = get_connection()
    conn.execute(
        text("DELETE FROM expenses WHERE id = :id"), {"id": expense_id}
    )
    conn.commit()
    bump_data_version()
