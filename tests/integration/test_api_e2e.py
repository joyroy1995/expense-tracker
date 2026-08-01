"""End-to-end integration tests for all API endpoints."""

import json
from unittest.mock import ANY, patch, MagicMock
from datetime import datetime
import database as db
from config import TIMEZONE


# ── Auth APIs ──────────────────────────────────────────────────

class TestAuthAPI:
    """POST /api/register, POST /api/login, POST /api/logout, GET /api/me"""

    def test_register_success(self, client, db_conn):
        resp = client.post("/api/register", json={
            "username": "newuser", "password": "pass1234", "confirm": "pass1234",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["username"] == "newuser"
        assert "id" in data

    def test_register_username_too_short(self, client):
        resp = client.post("/api/register", json={
            "username": "ab", "password": "pass1234", "confirm": "pass1234",
        })
        assert resp.status_code == 400
        assert "at least 3" in resp.get_json()["error"]

    def test_register_password_too_short(self, client):
        resp = client.post("/api/register", json={
            "username": "validusr", "password": "abc", "confirm": "abc",
        })
        assert resp.status_code == 400
        assert "at least 4" in resp.get_json()["error"]

    def test_register_password_mismatch(self, client):
        resp = client.post("/api/register", json={
            "username": "validusr", "password": "pass1234", "confirm": "different",
        })
        assert resp.status_code == 400
        assert "do not match" in resp.get_json()["error"]

    def test_register_missing_fields(self, client):
        resp = client.post("/api/register", json={"username": ""})
        assert resp.status_code == 400

    def test_register_duplicate_username(self, client, seed_user):
        resp = client.post("/api/register", json={
            "username": "testuser", "password": "pass1234", "confirm": "pass1234",
        })
        assert resp.status_code == 400
        assert "already taken" in resp.get_json()["error"]

    def test_login_success(self, client, seed_user):
        resp = client.post("/api/login", json={
            "username": "testuser", "password": "testpass",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["username"] == "testuser"

    def test_login_invalid_password(self, client, seed_user):
        resp = client.post("/api/login", json={
            "username": "testuser", "password": "wrongpass",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/login", json={
            "username": "nobody", "password": "pass",
        })
        assert resp.status_code == 401

    def test_logout(self, client):
        resp = client.post("/api/logout")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_me_authenticated(self, auth_client):
        resp = auth_client.get("/api/me")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["username"] == "testuser"

    def test_me_unauthenticated(self, client):
        resp = client.get("/api/me")
        assert resp.status_code == 401

    def test_register_sets_session(self, client, db_conn):
        resp = client.post("/api/register", json={
            "username": "another", "password": "pass1234", "confirm": "pass1234",
        })
        assert resp.status_code == 200
        # Verify session set by calling /api/me
        me = client.get("/api/me")
        assert me.status_code == 200
        assert me.get_json()["username"] == "another"


# ── Password Reset API ─────────────────────────────────────────

class TestPasswordResetAPI:
    """POST /api/forgot-password, GET /api/reset/<token>, POST /api/reset-password/<token>"""

    def test_forgot_password_nonexistent_user(self, client):
        resp = client.post("/api/forgot-password", json={"username": "ghost"})
        assert resp.status_code == 404

    def test_forgot_password_success(self, client, seed_user):
        resp = client.post("/api/forgot-password", json={"username": "testuser"})
        assert resp.status_code == 200
        assert "token" in resp.get_json()

    def test_validate_reset_token_valid(self, client, seed_user, db_conn):
        resp = client.post("/api/forgot-password", json={"username": "testuser"})
        token = resp.get_json()["token"]
        resp2 = client.get(f"/api/reset/{token}")
        assert resp2.status_code == 200
        assert resp2.get_json()["valid"] is True

    def test_validate_reset_token_invalid(self, client):
        resp = client.get("/api/reset/invalidtoken123")
        assert resp.status_code == 400

    def test_reset_password_success(self, client, seed_user, db_conn):
        resp = client.post("/api/forgot-password", json={"username": "testuser"})
        token = resp.get_json()["token"]
        resp2 = client.post(f"/api/reset-password/{token}", json={
            "password": "newpass123", "confirm": "newpass123",
        })
        assert resp2.status_code == 200
        assert resp2.get_json()["success"] is True

    def test_reset_password_mismatch(self, client, seed_user, db_conn):
        resp = client.post("/api/forgot-password", json={"username": "testuser"})
        token = resp.get_json()["token"]
        resp2 = client.post(f"/api/reset-password/{token}", json={
            "password": "newpass", "confirm": "different",
        })
        assert resp2.status_code == 400

    def test_reset_password_too_short(self, client, seed_user, db_conn):
        resp = client.post("/api/forgot-password", json={"username": "testuser"})
        token = resp.get_json()["token"]
        resp2 = client.post(f"/api/reset-password/{token}", json={
            "password": "abc", "confirm": "abc",
        })
        assert resp2.status_code == 400


# ── Profile API ────────────────────────────────────────────────

class TestProfileAPI:
    """GET /api/profile, POST /api/profile/change-password"""

    def test_profile_requires_auth(self, client):
        resp = client.get("/api/profile")
        assert resp.status_code == 401

    def test_profile_success(self, auth_client):
        resp = auth_client.get("/api/profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_count" in data
        assert "total_amount" in data
        assert data["username"] == "testuser"

    def test_change_password_success(self, auth_client, db_conn):
        resp = auth_client.post("/api/profile/change-password", json={
            "current_password": "testpass",
            "new_password": "newlongpass",
            "confirm_password": "newlongpass",
        })
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_change_password_wrong_current(self, auth_client):
        resp = auth_client.post("/api/profile/change-password", json={
            "current_password": "wrong",
            "new_password": "newlongpass",
            "confirm_password": "newlongpass",
        })
        assert resp.status_code == 400

    def test_change_password_too_short(self, auth_client):
        resp = auth_client.post("/api/profile/change-password", json={
            "current_password": "testpass",
            "new_password": "abc",
            "confirm_password": "abc",
        })
        assert resp.status_code == 400

    def test_change_password_mismatch(self, auth_client):
        resp = auth_client.post("/api/profile/change-password", json={
            "current_password": "testpass",
            "new_password": "newlongpass",
            "confirm_password": "different",
        })
        assert resp.status_code == 400


# ── Index / Dashboard API ──────────────────────────────────────

class TestIndexAPI:
    """GET /api/index"""

    def test_index_requires_auth(self, client):
        resp = client.get("/api/index")
        assert resp.status_code == 401

    def test_index_success(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/index")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "today" in data
        assert "today_total" in data
        assert "month_total" in data
        assert "today_expenses" in data
        assert "budget_alerts" in data


class TestDashboardAPI:
    """GET /api/dashboard"""

    def test_dashboard_requires_auth(self, client):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 401

    def test_dashboard_success(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "category_totals" in data
        assert "monthly_totals" in data
        assert "month_total" in data
        assert "month_expenses" in data
        assert "year" in data
        assert "month" in data

    def test_dashboard_with_search(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/dashboard?search=lunch")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["month_expenses"]) >= 1

    def test_dashboard_with_year_month(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/dashboard?year=2025&month=6")
        assert resp.status_code == 200

    def test_dashboard_superuser_can_filter_users(self, auth_client, superuser_client, seed_expenses):
        resp = superuser_client.get("/api/dashboard?user_id=9999")
        assert resp.status_code == 200


# ── Categories API ─────────────────────────────────────────────

class TestCategoriesAPI:
    """GET /api/categories"""

    def test_categories_requires_auth(self, client):
        resp = client.get("/api/categories")
        assert resp.status_code == 401

    def test_categories_success(self, auth_client):
        resp = auth_client.get("/api/categories")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "categories" in data
        assert "colors" in data
        assert "Food" in data["categories"]
        assert "Transport" in data["categories"]


# ── Learn API ──────────────────────────────────────────────────

class TestLearnAPI:
    """POST /api/learn"""

    def test_learn_requires_auth(self, client):
        resp = client.post("/api/learn", json={"description": "kacchi", "category": "Food"})
        assert resp.status_code == 401

    def test_learn_success(self, auth_client, db_conn):
        resp = auth_client.post("/api/learn", json={
            "description": "kacchi", "category": "Food",
        })
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_learn_missing_fields(self, auth_client):
        resp = auth_client.post("/api/learn", json={"description": ""})
        assert resp.status_code == 400

    def test_learn_no_keywords_produces_no_error(self, auth_client):
        resp = auth_client.post("/api/learn", json={
            "description": "tk", "category": "Food",
        })
        assert resp.status_code == 200


# ── Expense CRUD APIs ──────────────────────────────────────────

class TestExpenseCRUDAPI:
    """POST /api/add_expense, DELETE /api/delete_expense/<id>, GET /api/expenses/<date>,
       GET /api/expenses/month, GET /api/expenses/monthly-totals,
       GET /api/expenses/category-totals, GET /api/expenses/category-breakdown,
       GET /api/expenses/daily-totals"""

    def test_add_expense_requires_auth(self, client):
        resp = client.post("/api/add_expense", json={
            "description": "lunch", "amount": 100, "category": "Food",
        })
        assert resp.status_code == 401

    def test_add_expense_success(self, auth_client):
        resp = auth_client.post("/api/add_expense", json={
            "date": "2025-01-15", "description": "lunch", "amount": 150, "category": "Food",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["description"] == "lunch"
        assert data["amount"] == 150
        assert data["category"] == "Food"
        assert "id" in data

    def test_add_expense_no_description(self, auth_client):
        resp = auth_client.post("/api/add_expense", json={"description": ""})
        assert resp.status_code == 400

    def test_add_expense_with_learn(self, auth_client):
        resp = auth_client.post("/api/add_expense", json={
            "description": "kacchi",
            "amount": 500,
            "category": "Dining Out",
            "learn": True,
        })
        assert resp.status_code == 200

    def test_add_expense_auto_extract(self, auth_client):
        """Test with category/amount auto-prediction via LLM mock."""
        with patch("app.extract_expense") as mock_extract:
            mock_extract.return_value = {"category": "Food", "amount": 200}
            resp = auth_client.post("/api/add_expense", json={
                "description": "murgi 200 taka",
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["amount"] == 200
            assert data["category"] == "Food"

    def test_add_expense_grocery_subcategory(self, auth_client):
        resp = auth_client.post("/api/add_expense", json={
            "date": "2025-01-15",
            "description": "murgi kinlam 220",
            "amount": 220,
            "category": "Groceries",
            "subcategory": "Meat",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] == "Groceries"
        assert data["subcategory"] == "Meat"
        saved = db.get_expense_by_id(data["id"])
        assert saved["subcategory"] == "Meat"

    def test_add_expense_grocery_subcategory_invalid_falls_back(self, auth_client):
        resp = auth_client.post("/api/add_expense", json={
            "description": "aloo ar begun 120",
            "amount": 120,
            "category": "Groceries",
            "subcategory": "NotARealSubcat",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] == "Groceries"
        assert data["subcategory"] in ("Vegetables", "General")

    def test_add_expense_non_grocery_subcategory_cleared(self, auth_client):
        resp = auth_client.post("/api/add_expense", json={
            "description": "lunch",
            "amount": 150,
            "category": "Food",
            "subcategory": "Meat",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] == "Food"
        assert data["subcategory"] is None

    def test_add_expense_auto_extract_grocery_subcategory(self, auth_client):
        with patch("app.extract_expense") as mock_extract:
            mock_extract.return_value = {"category": "Groceries", "subcategory": "Meat", "amount": 220}
            resp = auth_client.post("/api/add_expense", json={"description": "murgi 220 taka"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["category"] == "Groceries"
            assert data["subcategory"] == "Meat"

    def test_update_expense_subcategory(self, auth_client):
        add = auth_client.post("/api/add_expense", json={
            "description": "mach 300",
            "amount": 300,
            "category": "Groceries",
            "subcategory": "General",
        })
        exp_id = add.get_json()["id"]
        resp = auth_client.put(f"/api/expenses/{exp_id}", json={
            "description": "mach 300",
            "amount": 300,
            "category": "Groceries",
            "subcategory": "Fish",
        })
        assert resp.status_code == 200
        assert resp.get_json()["subcategory"] == "Fish"
        resp2 = auth_client.put(f"/api/expenses/{exp_id}", json={
            "description": "mach 300",
            "amount": 300,
            "category": "Transport",
            "subcategory": "Fish",
        })
        assert resp2.status_code == 200
        assert resp2.get_json()["subcategory"] is None

    def test_delete_expense(self, auth_client, seed_expenses):
        # First add a known expense
        resp = auth_client.post("/api/add_expense", json={
            "description": "temp", "amount": 50, "category": "Food",
        })
        exp_id = resp.get_json()["id"]
        resp2 = auth_client.delete(f"/api/delete_expense/{exp_id}")
        assert resp2.status_code == 200
        assert resp2.get_json()["success"] is True

    def test_get_expenses_by_date(self, auth_client, seed_expenses):
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        resp = auth_client.get(f"/api/expenses/{today}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 2

    def test_get_expenses_by_month(self, auth_client, seed_expenses):
        now = datetime.now(TIMEZONE)
        resp = auth_client.get(f"/api/expenses/month?year={now.year}&month={now.month}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 2

    def test_monthly_totals(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/expenses/monthly-totals?months=3")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_category_totals(self, auth_client, seed_expenses):
        now = datetime.now(TIMEZONE)
        resp = auth_client.get(f"/api/expenses/category-totals?year={now.year}&month={now.month}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_category_breakdown_requires_params(self, auth_client):
        resp = auth_client.get("/api/expenses/category-breakdown")
        assert resp.status_code == 400

    def test_category_breakdown_success(self, auth_client, seed_expenses):
        now = datetime.now(TIMEZONE)
        resp = auth_client.get(
            f"/api/expenses/category-breakdown?year={now.year}&month={now.month}&category=Food"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "expenses" in data
        assert "total" in data

    def test_category_breakdown_groceries_subcategory_totals(self, auth_client):
        now = datetime.now(TIMEZONE)
        resp = auth_client.post("/api/expenses/bulk", json={
            "date": now.strftime("%Y-%m-%d"),
            "items": [
                {"description": "murgi", "amount": 220, "category": "Groceries", "subcategory": "Meat"},
                {"description": "mach", "amount": 300, "category": "Groceries", "subcategory": "Fish"},
                {"description": "murgi shobar jonna", "amount": 100, "category": "Groceries", "subcategory": "Meat"},
            ],
        })
        assert resp.get_json()["count"] == 3
        breakdown = auth_client.get(
            f"/api/expenses/category-breakdown?year={now.year}&month={now.month}&category=Groceries"
        )
        assert breakdown.status_code == 200
        data = breakdown.get_json()
        assert "subcategory_totals" in data
        totals = {t["subcategory"]: t["total"] for t in data["subcategory_totals"]}
        assert totals.get("Meat") == 320
        assert totals.get("Fish") == 300

    def test_daily_totals(self, auth_client, seed_expenses):
        now = datetime.now(TIMEZONE)
        resp = auth_client.get(f"/api/expenses/daily-totals?year={now.year}&month={now.month}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "totals" in data
        assert isinstance(data["totals"], dict)


# ── Expense Splitting ──────────────────────────────────────────

class TestSplitExpenseAPI:
    """POST /api/split_expense"""

    def test_split_requires_auth(self, client):
        resp = client.post("/api/split_expense", json={"description": "test"})
        assert resp.status_code == 401

    @patch("app.split_expenses")
    def test_split_success(self, mock_split, auth_client):
        mock_split.return_value = [
            {"description": "rice", "amount": 50, "category": "Food"},
            {"description": "chicken", "amount": 100, "category": "Food"},
        ]
        resp = auth_client.post("/api/split_expense", json={"description": "rice 50 chicken 100"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] is not None
        assert len(data["items"]) == 2

    def test_split_short_description(self, auth_client):
        resp = auth_client.post("/api/split_expense", json={"description": "x"})
        assert resp.status_code == 400

    @patch("app.split_expenses")
    def test_split_no_split_needed(self, mock_split, auth_client):
        mock_split.return_value = []
        resp = auth_client.post("/api/split_expense", json={"description": "single expense 200"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] is None


# ── Bulk Expense API ───────────────────────────────────────────

class TestBulkExpenseAPI:
    """POST /api/expenses/bulk"""

    def test_bulk_requires_auth(self, client):
        resp = client.post("/api/expenses/bulk", json={"items": []})
        assert resp.status_code == 401

    def test_bulk_empty_items(self, auth_client):
        resp = auth_client.post("/api/expenses/bulk", json={"items": []})
        assert resp.status_code == 400

    def test_bulk_success(self, auth_client):
        resp = auth_client.post("/api/expenses/bulk", json={
            "date": "2025-01-15",
            "items": [
                {"description": "rice", "amount": 50, "category": "Food"},
                {"description": "bus", "amount": 30, "category": "Transport"},
            ],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        assert len(data["expenses"]) == 2

    def test_bulk_grocery_subcategory(self, auth_client):
        resp = auth_client.post("/api/expenses/bulk", json={
            "date": "2025-01-15",
            "items": [
                {"description": "murgi 220", "amount": 220, "category": "Groceries", "subcategory": "Meat"},
                {"description": "aloo", "amount": 40, "category": "Groceries", "subcategory": "Vegetables"},
            ],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 2
        assert {e["subcategory"] for e in data["expenses"]} == {"Meat", "Vegetables"}

    def test_bulk_skips_invalid_items(self, auth_client):
        resp = auth_client.post("/api/expenses/bulk", json={
            "items": [
                {"description": "", "amount": 50, "category": "Food"},
                {"description": "valid", "amount": -1, "category": "Food"},
                {"description": "ok", "amount": 100, "category": "Food"},
            ],
        })
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 1


# ── Predict Expense API ────────────────────────────────────────

class TestPredictExpenseAPI:
    """POST /api/predict_expense"""

    def test_predict_requires_auth(self, client):
        resp = client.post("/api/predict_expense", json={"description": "lunch"})
        assert resp.status_code == 401

    @patch("app.predict_expense")
    def test_predict_success(self, mock_predict, auth_client):
        mock_predict.return_value = {"category": "Food", "amount": 200}
        resp = auth_client.post("/api/predict_expense", json={"description": "murgi 200"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] == "Food"

    @patch("app.predict_expense")
    def test_predict_grocery_subcategory(self, mock_predict, auth_client):
        mock_predict.return_value = {"category": "Groceries", "subcategory": "Meat", "amount": 220}
        resp = auth_client.post("/api/predict_expense", json={"description": "murgi 220"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] == "Groceries"
        assert data["subcategory"] == "Meat"
        assert data["amount"] == 220

    def test_predict_short_description(self, auth_client):
        resp = auth_client.post("/api/predict_expense", json={"description": "x"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] is None
        assert data["amount"] is None

    @patch("app.predict_expense")
    def test_predict_no_result(self, mock_predict, auth_client):
        mock_predict.return_value = None
        resp = auth_client.post("/api/predict_expense", json={"description": "something"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category"] is None
        assert data["amount"] is None


# ── Export API ─────────────────────────────────────────────────

class TestExportAPI:
    """GET /api/export/<fmt>"""

    def test_export_requires_auth(self, client):
        resp = client.get("/api/export/csv")
        assert resp.status_code == 401

    def test_export_csv(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/export/csv")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv"
        assert "expenses_" in resp.headers.get("Content-Disposition", "")

    def test_export_xlsx(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/export/xlsx")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type

    def test_export_pdf(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/export/pdf")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"

    def test_export_unsupported_format(self, auth_client):
        resp = auth_client.get("/api/export/doc")
        assert resp.status_code == 400

    def test_export_with_search(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/export/csv?search=lunch")
        assert resp.status_code == 200


# ── Budget APIs ────────────────────────────────────────────────

class TestBudgetAPI:
    """GET /api/budgets, POST /api/budgets/set, DELETE /api/budgets/delete/<id>,
       GET /api/budgets/status"""

    def test_get_budgets_requires_auth(self, client):
        resp = client.get("/api/budgets")
        assert resp.status_code == 401

    def test_get_budgets_empty(self, auth_client):
        resp = auth_client.get("/api/budgets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["budgets"] == []

    def test_set_budget_success(self, auth_client):
        resp = auth_client.post("/api/budgets/set", json={
            "category": "Food", "amount": 5000,
        })
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_set_budget_missing_category(self, auth_client):
        resp = auth_client.post("/api/budgets/set", json={"amount": 5000})
        assert resp.status_code == 400

    def test_set_budget_invalid_amount(self, auth_client):
        resp = auth_client.post("/api/budgets/set", json={
            "category": "Food", "amount": 0,
        })
        assert resp.status_code == 400

    def test_get_budgets_after_set(self, auth_client):
        auth_client.post("/api/budgets/set", json={"category": "Food", "amount": 5000})
        resp = auth_client.get("/api/budgets")
        data = resp.get_json()
        assert len(data["budgets"]) == 1
        assert data["budgets"][0]["category"] == "Food"
        assert data["budgets"][0]["amount"] == 5000

    def test_delete_budget(self, auth_client):
        auth_client.post("/api/budgets/set", json={"category": "Food", "amount": 5000})
        resp = auth_client.get("/api/budgets")
        budget_id = resp.get_json()["budgets"][0]["id"]
        resp2 = auth_client.delete(f"/api/budgets/delete/{budget_id}")
        assert resp2.status_code == 200
        resp3 = auth_client.get("/api/budgets")
        assert resp3.get_json()["budgets"] == []

    def test_budget_status(self, auth_client, seed_expenses):
        auth_client.post("/api/budgets/set", json={"category": "Food", "amount": 10000})
        resp = auth_client.get("/api/budgets/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "budget_status" in data

    def test_budget_status_with_month(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/budgets/status?month=2025-05")
        assert resp.status_code == 200


# ── Recurring Transactions API ─────────────────────────────────

class TestRecurringAPI:
    """GET/POST /api/recurring, PUT/DELETE /api/recurring/<id>,
       POST /api/recurring/process"""

    def test_get_recurring_requires_auth(self, client):
        resp = client.get("/api/recurring")
        assert resp.status_code == 401

    def test_get_recurring_empty(self, auth_client):
        resp = auth_client.get("/api/recurring")
        assert resp.status_code == 200
        assert resp.get_json()["transactions"] == []

    def test_create_recurring_success(self, auth_client):
        resp = auth_client.post("/api/recurring", json={
            "description": "Netflix",
            "amount": 799,
            "category": "Entertainment",
            "frequency": "monthly",
            "next_date": "2025-02-01",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "id" in data

    def test_create_recurring_missing_fields(self, auth_client):
        resp = auth_client.post("/api/recurring", json={"description": "test"})
        assert resp.status_code == 400

    def test_update_recurring(self, auth_client):
        create = auth_client.post("/api/recurring", json={
            "description": "Netflix", "amount": 799,
            "category": "Entertainment", "frequency": "monthly",
            "next_date": "2025-02-01",
        })
        rec_id = create.get_json()["id"]
        resp = auth_client.put(f"/api/recurring/{rec_id}", json={
            "amount": 999, "description": "Netflix Premium",
        })
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # Verify update
        get_resp = auth_client.get("/api/recurring")
        txns = get_resp.get_json()["transactions"]
        updated = [t for t in txns if t["id"] == rec_id][0]
        assert updated["amount"] == 999
        assert updated["description"] == "Netflix Premium"

    def test_delete_recurring(self, auth_client):
        create = auth_client.post("/api/recurring", json={
            "description": "Netflix", "amount": 799,
            "category": "Entertainment", "frequency": "monthly",
            "next_date": "2025-02-01",
        })
        rec_id = create.get_json()["id"]
        resp = auth_client.delete(f"/api/recurring/{rec_id}")
        assert resp.status_code == 200
        get_resp = auth_client.get("/api/recurring")
        assert len(get_resp.get_json()["transactions"]) == 0

    def test_process_recurring(self, auth_client):
        auth_client.post("/api/recurring", json={
            "description": "Rent", "amount": 15000,
            "category": "Rent", "frequency": "monthly",
            "next_date": "2020-01-01",
        })
        resp = auth_client.post("/api/recurring/process")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["processed"] == 1
        assert len(data["expenses"]) == 1


# ── Admin APIs ─────────────────────────────────────────────────

class TestAdminAPI:
    """GET /api/admin/users, POST .../change-role, POST .../delete"""

    def test_admin_requires_superuser(self, auth_client):
        resp = auth_client.get("/api/admin/users")
        assert resp.status_code == 403

    def test_admin_list_users(self, superuser_client, seed_user):
        resp = superuser_client.get("/api/admin/users")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "users" in data
        assert len(data["users"]) >= 1

    def test_admin_change_role(self, superuser_client, seed_user, db_conn):
        import database as db
        from werkzeug.security import generate_password_hash
        now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        pw = generate_password_hash("pass")
        result = db_conn.execute(
            db.text("INSERT INTO users (username, password_hash, role, created_at) VALUES (:u, :p, :r, :c)"),
            {"u": "otheruser", "p": pw, "r": "user", "c": now},
        )
        db_conn.commit()
        if hasattr(result, 'lastrowid'):
            other_id = result.lastrowid
        else:
            other_id = db_conn.execute(db.text("SELECT id FROM users WHERE username = 'otheruser'")).fetchone()[0]

        resp = superuser_client.post(f"/api/admin/users/{other_id}/change-role")
        assert resp.status_code == 200
        assert resp.get_json()["new_role"] == "superuser"

    def test_admin_cannot_change_own_role(self, superuser_client, seed_user):
        resp = superuser_client.post(f"/api/admin/users/{seed_user}/change-role")
        assert resp.status_code == 400

    def test_admin_delete_user(self, superuser_client, seed_user, db_conn):
        import database as db
        from werkzeug.security import generate_password_hash
        now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        pw = generate_password_hash("pass")
        db_conn.execute(
            db.text("INSERT INTO users (username, password_hash, role, created_at) VALUES (:u, :p, :r, :c)"),
            {"u": "delete_me", "p": pw, "r": "user", "c": now},
        )
        db_conn.commit()
        result = db_conn.execute(db.text("SELECT id FROM users WHERE username = 'delete_me'"))
        other_id = result.fetchone()[0]

        resp = superuser_client.post(f"/api/admin/users/{other_id}/delete")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_admin_cannot_delete_self(self, superuser_client, seed_user):
        resp = superuser_client.post(f"/api/admin/users/{seed_user}/delete")
        assert resp.status_code == 400


# ── Forecast API ───────────────────────────────────────────────

class TestForecastAPI:
    """GET /api/forecast"""

    def test_forecast_requires_auth(self, client):
        resp = client.get("/api/forecast")
        assert resp.status_code == 401

    @patch("app.generate_forecast")
    def test_forecast_success(self, mock_forecast, auth_client, seed_expenses):
        mock_forecast.return_value = {
            "projected": 25000,
            "confidence": "medium",
            "reasoning": "Based on current trends",
            "best_case": 20000,
            "worst_case": 30000,
            "notes": "",
        }
        resp = auth_client.get("/api/forecast")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "projected" in data
        assert "status" in data
        assert "daily_avg" in data

    def test_forecast_no_budget(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/forecast")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "no_budget"


# ── Transcribe API ─────────────────────────────────────────────

class TestTranscribeAPI:
    """POST /api/transcribe"""

    def test_transcribe_requires_auth(self, client):
        resp = client.post("/api/transcribe", data={})
        assert resp.status_code == 401

    def test_transcribe_no_audio(self, auth_client):
        resp = auth_client.post("/api/transcribe", data={})
        assert resp.status_code == 400

    @patch("app.transcribe_audio")
    def test_transcribe_success(self, mock_transcribe, auth_client):
        mock_transcribe.return_value = "kacchi khailam 500 taka"
        resp = auth_client.post(
            "/api/transcribe",
            data={"audio": (b"fake-audio-data", "recording.webm")},
            content_type="multipart/form-data",
        )
        # Flask test client doesn't send file properly via data; use buffered dict
        import io
        data = {"audio": (io.BytesIO(b"fake-audio"), "recording.webm")}
        resp2 = auth_client.post(
            "/api/transcribe",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["text"] == "kacchi khailam 500 taka"

    @patch("app.transcribe_audio")
    def test_transcribe_error(self, mock_transcribe, auth_client):
        mock_transcribe.side_effect = ValueError("Transcription failed")
        import io
        data = {"audio": (io.BytesIO(b"fake-audio"), "recording.webm")}
        resp = auth_client.post(
            "/api/transcribe",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 500


# ── Receipt Scan API ───────────────────────────────────────────

class TestReceiptScanAPI:
    """POST /api/scan_receipt"""

    def test_scan_requires_auth(self, client):
        resp = client.post("/api/scan_receipt", data={})
        assert resp.status_code == 401

    def test_scan_no_image(self, auth_client):
        resp = auth_client.post("/api/scan_receipt", data={})
        assert resp.status_code == 400

    @patch("app.scan_receipt")
    def test_scan_success(self, mock_scan, auth_client):
        import io
        mock_scan.return_value = {"items": [
            {"description": "Rice", "amount": 60, "category": "Groceries"},
        ]}
        data = {"image": (io.BytesIO(b"fake-image"), "receipt.jpg")}
        resp = auth_client.post(
            "/api/scan_receipt",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200

    @patch("app.scan_receipt")
    def test_scan_error(self, mock_scan, auth_client):
        import io
        mock_scan.side_effect = RuntimeError("Scan failed")
        data = {"image": (io.BytesIO(b"fake-image"), "receipt.jpg")}
        resp = auth_client.post(
            "/api/scan_receipt",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 500

    @patch("app.scan_receipt")
    def test_scan_no_items(self, mock_scan, auth_client):
        import io
        mock_scan.return_value = {"error": "No items found", "items": []}
        data = {"image": (io.BytesIO(b"fake-image"), "receipt.jpg")}
        resp = auth_client.post(
            "/api/scan_receipt",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 422


# ── Suggestions API ────────────────────────────────────────────

class TestSuggestionsAPI:
    """GET /api/suggestions"""

    def test_suggestions_requires_auth(self, client):
        resp = client.get("/api/suggestions")
        assert resp.status_code == 401

    def test_suggestions_success(self, auth_client, seed_expenses):
        resp = auth_client.get("/api/suggestions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) <= 4

    def test_suggestions_empty_returns_fallbacks(self, auth_client):
        resp = auth_client.get("/api/suggestions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["suggestions"]) >= 1


# ── Q&A / Chat API ─────────────────────────────────────────────

class TestAskAPI:
    """POST /api/ask"""

    def test_ask_requires_auth(self, client):
        resp = client.post("/api/ask", json={"question": "how much?"})
        assert resp.status_code == 401

    def test_ask_empty_question(self, auth_client):
        resp = auth_client.post("/api/ask", json={"question": ""})
        assert resp.status_code == 400

    def test_ask_generates_sql(self, auth_client, seed_expenses):
        """Test the full pipeline with mocked LLM SQL generation."""
        with patch("services.qa_service.generate_sql") as mock_gen:
            mock_gen.return_value = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
            resp = auth_client.post("/api/ask", json={"question": "how much did I spend?"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert "answer" in data
            assert "sql" in data

    def test_ask_with_bad_sql_returns_error(self, auth_client, seed_expenses):
        with patch("services.qa_service.generate_sql") as mock_gen:
            mock_gen.return_value = "DROP TABLE expenses"
            resp = auth_client.post("/api/ask", json={"question": "generate a bad sql query"})
            assert resp.status_code == 500
            data = resp.get_json()
            assert "error" in data or "sql" in data

    def test_ask_decomposes_question(self, auth_client, seed_expenses):
        with patch("services.qa_service.decompose_question") as mock_decomp, \
             patch("services.qa_service.generate_sql") as mock_gen:
            mock_decomp.return_value = ["how much on food?", "how much on transport?"]
            mock_gen.return_value = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date LIKE '2025-06%' AND user_id = :uid"
            resp = auth_client.post("/api/ask", json={
                "question": "compare food and transport",
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert "answer" in data


class TestChatAPI:
    """POST /api/chat"""

    def test_chat_requires_auth(self, client):
        resp = client.post("/api/chat", json={"message": "hello"})
        assert resp.status_code == 401

    def test_chat_short_message(self, auth_client):
        resp = auth_client.post("/api/chat", json={"message": "x"})
        assert resp.status_code == 400

    def test_chat_expense_intent(self, auth_client):
        with patch("app.is_question") as mock_is_q, \
             patch("app.split_expenses") as mock_split:
            mock_is_q.return_value = False
            mock_split.return_value = [
                {"description": "lunch", "amount": 150, "category": "Food"},
            ]
            resp = auth_client.post("/api/chat", json={
                "message": "lunch 150",
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["type"] == "expense"
            assert "items" in data

    def test_chat_budget_intent_detected(self, auth_client):
        with patch("app.detect_budget_intent") as mock_budget:
            mock_budget.return_value = {"category": "Food", "amount": 5000}
            resp = auth_client.post("/api/chat", json={
                "message": "set food budget 5000",
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["type"] == "budget"

    def test_chat_question_intent(self, auth_client, seed_expenses):
        with patch("app.is_question") as mock_is_q, \
             patch("services.qa_service.generate_sql") as mock_gen, \
             patch("services.qa_service.decompose_question") as mock_decomp:
            mock_is_q.return_value = True
            mock_decomp.return_value = []
            mock_gen.return_value = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
            resp = auth_client.post("/api/chat", json={
                "message": "how much did I spend?",
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["type"] == "question"
            assert "answer" in data


# ── Notifications API ──────────────────────────────────────────

class TestNotificationsAPI:
    """GET /api/notifications/vapid-public-key,
       POST /api/notifications/subscribe, POST /api/notifications/unsubscribe,
       POST /api/notifications/check-digest"""

    @patch("services.notification_service.NotificationService.load_vapid")
    def test_vapid_public_key_not_configured(self, mock_load, client):
        mock_load.return_value = (None, None)
        resp = client.get("/api/notifications/vapid-public-key")
        assert resp.status_code == 500

    def test_subscribe_requires_auth(self, client):
        resp = client.post("/api/notifications/subscribe", json={})
        assert resp.status_code == 401

    def test_subscribe_missing_fields(self, auth_client):
        resp = auth_client.post("/api/notifications/subscribe", json={})
        assert resp.status_code == 400

    def test_unsubscribe_requires_auth(self, client):
        resp = client.post("/api/notifications/unsubscribe", json={})
        assert resp.status_code == 401

    def test_check_digest_requires_auth(self, client):
        resp = client.post("/api/notifications/check-digest")
        assert resp.status_code == 401

    def test_check_digest_no_subscription(self, auth_client):
        resp = auth_client.post("/api/notifications/check-digest")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "no_subscription"


# ── Admin Daily Digest Trigger ─────────────────────────────────

class TestAdminDigestAPI:
    """POST /api/admin/notifications/daily-digest/trigger"""

    def test_digest_trigger_requires_superuser(self, auth_client):
        resp = auth_client.post("/api/admin/notifications/daily-digest/trigger")
        assert resp.status_code == 403

    def test_digest_trigger(self, superuser_client):
        resp = superuser_client.post("/api/admin/notifications/daily-digest/trigger")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sent" in data
        assert "failed" in data
