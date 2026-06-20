from datetime import datetime
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection


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
