from datetime import datetime, timedelta
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection


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
