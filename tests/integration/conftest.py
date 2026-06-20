import os
import pytest
from unittest.mock import MagicMock, patch
from config import DATABASE_URL as _orig_db_url, DATABASE_PATH as _orig_db_path
import database as db
from database import engine as _db_engine
from app import app as _flask_app


@pytest.fixture(autouse=True)
def reset_db():
    old_url = _orig_db_url
    old_path = _orig_db_path
    old_engine = _db_engine._engine
    old_init = _db_engine._db_init_done

    _db_engine.DATABASE_URL = ""
    _db_engine.DATABASE_PATH = ":memory:"
    _db_engine._engine = None
    _db_engine._db_init_done = False

    yield

    _db_engine.DATABASE_URL = old_url
    _db_engine.DATABASE_PATH = old_path
    _db_engine._engine = old_engine
    _db_engine._db_init_done = old_init


@pytest.fixture
def app():
    _flask_app.config['TESTING'] = True
    _flask_app.config['SECRET_KEY'] = 'test-secret-key'
    return _flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture
def db_conn():
    return db.get_connection()


@pytest.fixture
def seed_user(db_conn):
    from werkzeug.security import generate_password_hash
    from datetime import datetime
    from config import TIMEZONE
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    pw = generate_password_hash("testpass")
    result = db_conn.execute(
        db.text("INSERT INTO users (username, password_hash, role, created_at) VALUES (:u, :p, :r, :c)"),
        {"u": "testuser", "p": pw, "r": "user", "c": now},
    )
    db_conn.commit()
    return result.lastrowid


@pytest.fixture
def seed_expenses(db_conn, seed_user):
    from datetime import datetime
    from config import TIMEZONE
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    expenses_data = [
        {"date": today, "description": "lunch", "amount": 350.0, "category": "Food", "user_id": seed_user},
        {"date": today, "description": "bus", "amount": 30.0, "category": "Transport", "user_id": seed_user},
        {"date": "2025-06-01", "description": "rent", "amount": 15000.0, "category": "Rent", "user_id": seed_user},
        {"date": "2025-05-15", "description": "groceries", "amount": 2000.0, "category": "Groceries", "user_id": seed_user},
    ]
    for e in expenses_data:
        db_conn.execute(
            db.text("INSERT INTO expenses (date, description, amount, category, user_id) VALUES (:d, :desc, :a, :cat, :uid)"),
            {"d": e["date"], "desc": e["description"], "a": e["amount"], "cat": e["category"], "uid": e["user_id"]},
        )
    db_conn.commit()
    return seed_user


@pytest.fixture
def auth_client(client, seed_user):
    with client.session_transaction() as sess:
        sess["user_id"] = seed_user
        sess["username"] = "testuser"
        sess["role"] = "user"
    return client


@pytest.fixture
def superuser_client(client, seed_user):
    db_conn = db.get_connection()
    db_conn.execute(
        db.text("UPDATE users SET role = 'superuser' WHERE id = :id"),
        {"id": seed_user},
    )
    db_conn.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = seed_user
        sess["username"] = "testuser"
        sess["role"] = "superuser"
    return client


def mock_groq_response(content):
    """Create a mock Groq API response with the given content string."""
    mock_msg = MagicMock()
    mock_msg.message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_msg.message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response
