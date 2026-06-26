import json
import hashlib
from datetime import datetime
from sqlalchemy import text
from config import TIMEZONE
from database.engine import get_connection, bump_data_version

_ADVISOR_CACHE_TTL_SECONDS = 86400
_ADVISOR_CACHE_VERSION = 2


def _ensure_table():
    conn = get_connection()
    from database.engine import _is_postgres
    if _is_postgres():
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS advisor_cache (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                month TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, month)
            )
        """))
    else:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS advisor_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, month),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """))
    conn.commit()


def get_cached_advisor(user_id, month):
    _ensure_table()
    conn = get_connection()
    row = conn.execute(
        text("""
            SELECT response_json, created_at
            FROM advisor_cache
            WHERE user_id = :uid AND month = :m
            ORDER BY created_at DESC LIMIT 1
        """),
        {"uid": user_id, "m": month},
    ).fetchone()
    if not row:
        return None
    created_at = row[1]
    if isinstance(created_at, str):
        created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    created_at = created_at.replace(tzinfo=TIMEZONE)
    age = datetime.now(TIMEZONE) - created_at
    if age.total_seconds() > _ADVISOR_CACHE_TTL_SECONDS:
        return None
    data = json.loads(row[0])
    if data.get("_cache_version", 0) != _ADVISOR_CACHE_VERSION:
        return None
    return data


def set_cached_advisor(user_id, month, data):
    _ensure_table()
    data["_cache_version"] = _ADVISOR_CACHE_VERSION
    conn = get_connection()
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        text("""
            DELETE FROM advisor_cache WHERE user_id = :uid AND month = :m
        """),
        {"uid": user_id, "m": month},
    )
    conn.execute(
        text("""
            INSERT INTO advisor_cache (user_id, month, response_json, created_at)
            VALUES (:uid, :m, :rj, :n)
        """),
        {"uid": user_id, "m": month, "rj": json.dumps(data), "n": now},
    )
    conn.commit()
    bump_data_version()


def clear_advisor_cache(user_id=None, month=None):
    _ensure_table()
    conn = get_connection()
    if user_id and month:
        conn.execute(
            text("DELETE FROM advisor_cache WHERE user_id = :uid AND month = :m"),
            {"uid": user_id, "m": month},
        )
    elif user_id:
        conn.execute(
            text("DELETE FROM advisor_cache WHERE user_id = :uid"),
            {"uid": user_id},
        )
    else:
        conn.execute(text("DELETE FROM advisor_cache"))
    conn.commit()
    bump_data_version()
