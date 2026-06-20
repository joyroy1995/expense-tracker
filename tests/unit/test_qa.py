import pytest
from llm.qa import _fmt_history, _display_cat, format_answer


class TestFmtHistory:
    def test_empty_history(self):
        assert _fmt_history(None) == ""
        assert _fmt_history([]) == ""

    def test_single_entry(self):
        history = [{"role": "user", "content": "hello"}]
        result = _fmt_history(history)
        assert "User: hello" in result
        assert "Conversation history:" in result

    def test_multiple_entries(self):
        history = [
            {"role": "user", "content": "how much on food"},
            {"role": "assistant", "content": "Your total is 500"},
        ]
        result = _fmt_history(history)
        assert "User: how much on food" in result
        assert "Assistant: Your total is 500" in result

    def test_max_entries_respected(self):
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = _fmt_history(history, max_entries=3)
        assert "msg7" in result
        assert "msg0" not in result

    def test_max_entries_default(self):
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = _fmt_history(history)
        assert "msg4" in result
        assert "msg0" not in result


class TestDisplayCat:
    def test_overall(self):
        assert _display_cat("__overall__") == "Overall"

    def test_normal_category(self):
        assert _display_cat("Food") == "Food"

    def test_empty_string(self):
        assert _display_cat("") == ""

    def test_none(self):
        assert _display_cat(None) == ""


class TestFormatAnswer:
    def test_empty_data(self):
        result = format_answer(["total"], [], "question")
        assert result["text"] == "No expenses found matching your question."
        assert result["type"] == "text"

    def test_single_total(self):
        data = [{"total": 500.0}]
        result = format_answer(["total"], data, "how much")
        assert "500" in result["text"]
        assert result["type"] == "total"

    def test_single_total_and_count(self):
        data = [{"total": 500.0, "count": 3}]
        result = format_answer(["total", "count"], data, "how much")
        assert "500" in result["text"]
        assert "3" in result["text"]
        assert result["type"] == "total"

    def test_budget_remaining(self):
        data = [{"category": "Food", "budget_amount": 5000.0, "spent": 3000.0, "remaining": 2000.0}]
        result = format_answer(["category", "budget_amount", "spent", "remaining"], data, "budget")
        assert "remaining" in result["text"]
        assert result["type"] == "budget"
        assert result["remaining"] == 2000.0

    def test_budget_exceeded(self):
        data = [{"category": "Food", "budget_amount": 5000.0, "spent": 6000.0, "remaining": -1000.0}]
        result = format_answer(["category", "budget_amount", "spent", "remaining"], data, "budget")
        assert "exceeded" in result["text"]
        assert result["type"] == "budget"
        assert result["remaining"] == -1000.0

    def test_budget_exact(self):
        data = [{"category": "Food", "budget_amount": 5000.0, "spent": 5000.0, "remaining": 0.0}]
        result = format_answer(["category", "budget_amount", "spent", "remaining"], data, "budget")
        assert "entire budget" in result["text"]
        assert result["type"] == "budget"

    def test_pacing(self):
        data = [{"total": 15000.0, "daily_avg": 500.0, "days_elapsed": 30, "days_in_month": 30}]
        result = format_answer(["total", "daily_avg", "days_elapsed", "days_in_month"], data, "on track")
        assert result["type"] == "pacing"

    def test_monthly_comparison(self):
        data = [
            {"month": "2025-05", "total": 10000.0},
            {"month": "2025-06", "total": 15000.0},
        ]
        result = format_answer(["month", "total"], data, "compare months")
        assert result["type"] == "comparison"
        assert len(result["months"]) == 2

    def test_single_comparison_no_compare(self):
        data = [{"month": "2025-06", "total": 15000.0}]
        result = format_answer(["month", "total"], data, "single month")
        assert result["type"] != "comparison"

    def test_average(self):
        data = [{"avg_daily": 500.0, "count": 15}]
        result = format_answer(["avg_daily", "count"], data, "average")
        assert result["type"] == "average"
        assert result["avg"] == 500.0

    def test_average_no_count(self):
        data = [{"avg": 500.0}]
        result = format_answer(["avg"], data, "average")
        assert result["type"] == "average"

    def test_single_expense(self):
        data = [{"description": "lunch", "amount": 350.0, "date": "2025-06-15", "category": "Food"}]
        result = format_answer(["description", "amount", "date", "category"], data, "what is this")
        assert result["type"] == "expense"
        assert result["description"] == "lunch"

    def test_single_expense_no_date(self):
        data = [{"description": "lunch", "amount": 350.0, "category": "Food"}]
        result = format_answer(["description", "amount", "category"], data, "what is this")
        assert result["type"] == "expense"

    def test_most_expensive(self):
        data = [{"max": 5000.0, "description": "rent", "category": "Rent"}]
        result = format_answer(["max", "description", "category"], data, "most expensive")
        assert result["type"] == "extremum"
        assert result["is_max"] is True

    def test_least_expensive(self):
        data = [{"min": 10.0, "description": "tea", "category": "Food"}]
        result = format_answer(["min", "description", "category"], data, "least expensive")
        assert result["type"] == "extremum"
        assert result["is_max"] is False

    def test_category_breakdown(self):
        data = [
            {"category": "Food", "total": 5000.0},
            {"category": "Transport", "total": 3000.0},
        ]
        result = format_answer(["category", "total"], data, "breakdown by category")
        assert result["type"] == "category_breakdown"
        assert len(result["categories"]) == 2

    def test_frequency_single(self):
        data = [{"category": "Food", "count": 15}]
        result = format_answer(["category", "count"], data, "most used category")
        assert result["type"] == "frequency"
        assert result["category"] == "Food"

    def test_fallback_list(self):
        data = [{"amount": 100.0}, {"amount": 200.0}]
        result = format_answer(["amount"], data, "show some")
        assert "Found 2 result(s)" in result["text"]
        assert result["type"] == "list"
