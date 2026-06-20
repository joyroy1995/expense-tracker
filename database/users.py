from datetime import datetime, timedelta
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection, _is_postgres
import secrets


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
