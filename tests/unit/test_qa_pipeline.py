import re
import pytest
from unittest import mock
from datetime import date
from services.pattern_engine import PatternEngine
from services.sql_service import SqlService
from services.qa_service import QaService

FIXED_DATE = date(2025, 6, 15)


@pytest.fixture
def engine():
    with mock.patch("services.pattern_engine._fmt_dates") as mock_fmt:
        mock_fmt.return_value = {
            "today": "2025-06-15",
            "current_month": "2025-06",
            "last_month": "2025-05",
            "current_year": "2025",
            "seven_days_ago": "2025-06-08",
            "week_start": "2025-06-09",
            "last_week_start": "2025-06-02",
            "yesterday": "2025-06-14",
            "days_elapsed": 15,
            "days_in_month": 30,
        }
        return PatternEngine()


def _month(d):
    return d.strftime("%Y-%m")


def _prev_month(d):
    prev = d.replace(day=1)
    from datetime import timedelta
    prev -= timedelta(days=1)
    return prev.strftime("%Y-%m")


def _week_start(d):
    from datetime import timedelta
    return (d - timedelta(days=d.weekday())).isoformat()


def _last_week_start(d):
    from datetime import timedelta
    return (d - timedelta(days=d.weekday() + 7)).isoformat()


# ── Banglish Normalization ──

class TestBanglishNormalization:
    def test_ajke_to_today(self):
        assert QaService.normalize_question("ajke khoroch koto") == "today spending how much"

    def test_gotokal_to_yesterday(self):
        assert QaService.normalize_question("gotokal koto khoroch") == "yesterday how much spending"

    def test_kal_to_tomorrow(self):
        assert "tomorrow" in QaService.normalize_question("kal ki khoroch hobe")

    def test_ei_mash_to_this_month(self):
        assert QaService.normalize_question("ei mash e pouro khoroch") == "this month e total spending"

    def test_gotol_mash_to_last_month(self):
        result = QaService.normalize_question("gotol mash e koto khoroch")
        assert "last month" in result
        assert "how much" in result

    def test_koto_to_how_much(self):
        assert "how much" in QaService.normalize_question("ei mash e koto khoroch")

    def test_dekhau_to_show(self):
        assert QaService.normalize_question("sokol khoroch dekhau") == "sokol spending show"

    def test_pouro_to_total(self):
        assert QaService.normalize_question("ei mash er pouro khoroch") == "this month er total spending"

    def test_multiple_banglish_in_one_question(self):
        result = QaService.normalize_question("ajke gotokal ei mash er koto pouro")
        assert "today" in result
        assert "yesterday" in result
        assert "this month" in result
        assert "how much" in result
        assert "total" in result

    def test_koyta_to_how_many(self):
        assert "how many" in QaService.normalize_question("ei mash e koyta transaction")

    def test_khoroch_to_spending(self):
        assert QaService.normalize_question("moto khoroch") == "moto spending"


# ── Comparison normalization ──

class TestCompareNormalization:
    def test_this_month_vs_last_month(self):
        assert "How does this month compare to last month" in QaService.normalize_question(
            "this month vs last month"
        )

    def test_month_over_month(self):
        assert "How does this month compare to last month" in QaService.normalize_question(
            "month over month spending"
        )

    def test_compare_to_last_month(self):
        assert "How does this month compare to last month" in QaService.normalize_question(
            "compare to last month"
        )

    def test_already_long_form_unchanged(self):
        q = "How does this month compare to last month"
        assert QaService.normalize_question(q) == q


# ── Intent Classification ──

class TestClassifyIntent:
    def test_aggregate_intent(self):
        intent = SqlService._classify_intent("How much did I spend on food?")
        assert intent["is_aggregate"] is True
        assert intent["is_list"] is False

    def test_list_intent(self):
        intent = SqlService._classify_intent("Show all my expenses this month")
        assert intent["is_list"] is True
        assert intent["is_aggregate"] is False

    def test_breakdown_intent(self):
        intent = SqlService._classify_intent("Show me a category breakdown this month")
        assert intent["is_breakdown"] is True

    def test_frequency_intent(self):
        intent = SqlService._classify_intent("How many times did I dine out?")
        assert intent["is_frequency"] is True

    def test_budget_intent(self):
        intent = SqlService._classify_intent("How much budget left for Groceries?")
        assert intent["is_budget"] is True

    def test_most_expensive_intent(self):
        intent = SqlService._classify_intent("What was my most expensive expense?")
        assert intent["is_most_expensive"] is True

    def test_top_n_intent(self):
        intent = SqlService._classify_intent("Show top 5 expenses this month")
        assert intent["is_top_n"] is True

    def test_ordinal_intent(self):
        intent = SqlService._classify_intent("What was my second most expensive expense?")
        assert intent["is_ordinal"] is True

    def test_sort_request(self):
        intent = SqlService._classify_intent("Show expenses descending by date")
        assert intent["has_sort_request"] is True

    def test_no_intent_for_non_question(self):
        intent = SqlService._classify_intent("hello there")
        assert all(v is False for v in intent.values())


# ── Ellipsis / Context Carry-Over ──

class TestResolveEllipsis:
    def test_what_about_carries_previous_subject(self):
        from services.qa_service import resolve_ellipsis
        history = [{"role": "user", "content": "How much on Food this month?"}]
        result = resolve_ellipsis("what about last month?", history)
        assert "food" in result.lower()
        assert "last month" in result

    def test_how_about_carries_previous_subject(self):
        from services.qa_service import resolve_ellipsis
        history = [{"role": "user", "content": "How much on Transport this week?"}]
        result = resolve_ellipsis("how about this month?", history)
        assert "transport" in result.lower()

    def test_no_history_returns_original(self):
        from services.qa_service import resolve_ellipsis
        assert resolve_ellipsis("how much on food?", []) == "how much on food?"

    def test_no_ellipsis_returns_original(self):
        from services.qa_service import resolve_ellipsis
        history = [{"role": "user", "content": "How much on Food?"}]
        assert resolve_ellipsis("Show me everything", history) == "Show me everything"

    def test_and_what_about(self):
        from services.qa_service import resolve_ellipsis
        history = [{"role": "user", "content": "How much on Groceries this month?"}]
        result = resolve_ellipsis("and what about last week?", history)
        assert "groceries" in result.lower()


# ── SQL Injection Prevention ──

class TestSqlInjectionPrevention:
    def test_fix_description_filter_sanitizes_keyword(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = SqlService.fix_description_filter(sql, "How much on uber OR 1=1?")
        assert "1=1" not in result
        assert "uber" in result.lower()
        assert "LIKE" in result

    def test_fix_description_filter_rejects_empty_keyword(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = SqlService.fix_description_filter(sql, "Show me everything")
        assert result == sql

    def test_fix_description_filter_strips_non_alphanumeric(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = SqlService.fix_description_filter(sql, "how much on uber'--")
        assert "uber" in result.lower()
        assert "1=1" not in result


# ── Multi-Word Description Search ──

class TestMultiWordDescription:
    def test_multi_word_keyword_extraction(self):
        result = SqlService._extract_item_keyword("how much on uber eats this month?")
        assert result == "uber eats"

    def test_single_word_keyword_extraction(self):
        result = SqlService._extract_item_keyword("how much on pizza?")
        assert result == "pizza"

    def test_no_keyword_returns_none(self):
        result = SqlService._extract_item_keyword("what is my total spending?")
        assert result is None

    def test_sql_injection_keyword_sanitized(self):
        result = SqlService._extract_item_keyword("how much on food' or '1'='1?")
        assert result is not None
        assert "'" not in result


# ── Pattern Engine: How Much with Category ──

class TestPatternHowMuchCategory:
    def test_this_month_with_category(self, engine):
        result = engine.match("How much on Transport this month?")
        assert result is not None
        sql, pname = result
        assert pname == "how_much_category"
        assert "SUM(amount)" in sql
        assert "category = 'Transport'" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_last_month_with_category(self, engine):
        result = engine.match("How much did I spend on Food last month?")
        assert result is not None
        sql, pname = result
        assert pname == "how_much_category"
        assert "category = 'Food'" in sql
        assert "date LIKE '2025-05%'" in sql

    def test_today_with_category(self, engine):
        result = engine.match("How much on Groceries today?")
        assert result is not None
        sql, pname = result
        assert "category = 'Groceries'" in sql
        assert "date = '2025-06-15'" in sql

    def test_no_category_no_match(self, engine):
        result = engine.match("How much did I spend?")
        assert result is not None
        assert result[1] == "how_much_total"


# ── Pattern Engine: How Much Total ──

class TestPatternHowMuchTotal:
    def test_this_month_total(self, engine):
        result = engine.match("How much did I spend this month?")
        assert result is not None
        sql, pname = result
        assert pname == "how_much_total"
        assert "SUM(amount)" in sql
        assert "date LIKE '2025-06%'" in sql
        assert "category =" not in sql

    def test_no_time_no_category(self, engine):
        result = engine.match("How much did I spend?")
        assert result is not None
        sql, pname = result
        assert pname == "how_much_total"
        assert "user_id = :uid" in sql
        assert "COUNT(*)" in sql

    def test_last_7_days(self, engine):
        result = engine.match("How much did I spend in the last 7 days?")
        assert result is not None
        sql, pname = result
        assert pname == "how_much_total"
        assert "date >=" in sql
        assert "COUNT(*)" in sql


# ── Pattern Engine: Show Expenses ──

class TestPatternShowExpenses:
    def test_show_this_week(self, engine):
        result = engine.match("Show all expenses this week")
        assert result is not None
        sql, pname = result
        assert pname == "show_expenses"
        assert "date, description, amount, category" in sql
        assert "2025-06-09" in sql
        assert "ORDER BY date DESC LIMIT 50" in sql

    def test_show_yesterday(self, engine):
        result = engine.match("Show expenses yesterday")
        assert result is not None
        sql, pname = result
        assert pname == "show_expenses"
        assert "date = '2025-06-14'" in sql


class TestPatternShowByCategory:
    def test_show_transport_this_month(self, engine):
        result = engine.match("Show my Transport expenses this month")
        assert result is not None
        sql, pname = result
        assert pname == "show_expenses_by_category"
        assert "category = 'Transport'" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_no_time_no_match(self, engine):
        result = engine.match("Show Transport expenses")
        assert result is None


# ── Pattern Engine: How Many / Frequency ──

class TestPatternHowMany:
    def test_how_many_this_month(self, engine):
        result = engine.match("Count my expenses this month")
        assert result is not None
        sql, pname = result
        assert pname == "how_many"
        assert "COUNT(*) as count" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_how_many_last_month_with_category(self, engine):
        result = engine.match("How many times did I go to Dining Out last month?")
        assert result is not None
        sql, pname = result
        assert pname == "how_many"
        assert "category = 'Dining Out'" in sql
        assert "date LIKE '2025-05%'" in sql


# ── Pattern Engine: Top N ──

class TestPatternTopN:
    def test_top_5_this_month(self, engine):
        result = engine.match("Show top 5 expenses this month")
        assert result is not None
        sql, pname = result
        assert pname == "top_n"
        assert "ORDER BY amount DESC LIMIT 5" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_top_3_with_category(self, engine):
        result = engine.match("What are the top 3 Transport expenses?")
        assert result is not None
        sql, pname = result
        assert pname == "top_n"
        assert "LIMIT 3" in sql
        assert "category = 'Transport'" in sql


# ── Pattern Engine: Most Expensive ──

class TestPatternMostExpensive:
    def test_most_expensive_this_month(self, engine):
        result = engine.match("What was my most expensive expense this month?")
        assert result is not None
        sql, pname = result
        assert pname == "most_expensive"
        assert "ORDER BY amount DESC LIMIT 1" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_most_expensive_with_category(self, engine):
        result = engine.match("What was my most expensive Food expense?")
        assert result is not None
        sql, pname = result
        assert pname == "most_expensive"
        assert "category = 'Food'" in sql


# ── Pattern Engine: Category Breakdown ──

class TestPatternCategoryBreakdown:
    def test_breakdown_this_month(self, engine):
        result = engine.match("Show me a category breakdown this month")
        assert result is not None
        sql, pname = result
        assert pname == "category_breakdown"
        assert "GROUP BY category" in sql
        assert "ORDER BY total DESC" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_by_category_this_month(self, engine):
        result = engine.match("Show spending by category this month")
        assert result is not None
        assert result[1] == "category_breakdown"
        assert "GROUP BY category" in result[0]


# ── Pattern Engine: Average Daily ──

class TestPatternAverageDaily:
    def test_average_daily_this_month(self, engine):
        result = engine.match("What is my average daily spending this month?")
        assert result is not None
        sql, pname = result
        assert pname == "average_daily"
        assert "AVG(daily.total)" in sql
        assert "date LIKE '2025-06%'" in sql


# ── Pattern Engine: Comparison ──

class TestPatternComparison:
    def test_this_month_vs_last_month(self, engine):
        result = engine.match("How does this month compare to last month?")
        assert result is not None
        sql, pname = result
        assert pname == "month_comparison"
        assert "date LIKE '2025-06%'" in sql
        assert "date LIKE '2025-05%'" in sql
        assert "GROUP BY" in sql

    def test_vs_keyword(self, engine):
        result = engine.match("This month vs last month spending")
        assert result is not None
        sql, pname = result
        assert pname == "month_comparison"


# ── Pattern Engine: Week Comparison ──

class TestPatternWeekComparison:
    def test_week_over_week(self, engine):
        result = engine.match("How does this week compare to last week?")
        assert result is not None
        sql, pname = result
        assert pname == "week_comparison"
        assert "UNION ALL" in sql
        assert "This week" in sql
        assert "Last week" in sql
        assert "2025-06-09" in sql
        assert "2025-06-02" in sql


# ── Pattern Engine: Year Comparison ──

class TestPatternYearComparison:
    def test_year_over_year(self, engine):
        result = engine.match("How does this year compare to last year?")
        assert result is not None
        sql, pname = result
        assert pname == "year_comparison"
        assert "date LIKE '2025%'" in sql
        assert "date LIKE '2024%'" in sql


# ── Pattern Engine: Date Range ──

class TestPatternDateRange:
    def test_between_dates_aggregate(self, engine):
        result = engine.match("How much did I spend between June 1 and June 15?")
        assert result is not None
        sql, pname = result
        assert pname == "date_range"
        assert "SUM(amount)" in sql
        assert "2025-06-01" in sql
        assert "2025-06-15" in sql


# ── Pattern Engine: Combined Categories ──

class TestPatternCombinedCategories:
    def test_food_and_transport_combined(self, engine):
        result = engine.match("How much on Food and Transport combined this month")
        assert result is not None
        sql, pname = result
        assert pname == "combined_categories"
        assert "category IN (" in sql
        assert "'Food'" in sql
        assert "'Transport'" in sql
        assert "date LIKE '2025-06%'" in sql


# ── Pattern Engine: Amount Threshold ──

class TestPatternAmountThreshold:
    def test_over_500_this_month_list(self, engine):
        result = engine.match("Show expenses over 500 this month")
        assert result is not None
        sql, pname = result
        assert pname == "amount_threshold"
        assert "amount > 500" in sql
        assert "date LIKE '2025-06%'" in sql
        assert "ORDER BY amount DESC" in sql

    def test_under_1000_aggregate(self, engine):
        result = engine.match("How much did I spend under 1000 this month?")
        assert result is not None
        sql, pname = result
        assert pname == "amount_threshold"
        assert "amount < 1000" in sql
        assert "SUM(amount)" in sql


# ── Pattern Engine: Daily Breakdown ──

class TestPatternDailyBreakdown:
    def test_each_day_this_month(self, engine):
        result = engine.match("How much did I spend each day this month?")
        assert result is not None
        sql, pname = result
        assert pname == "daily_breakdown"
        assert "GROUP BY date" in sql
        assert "ORDER BY date" in sql
        assert "date LIKE '2025-06%'" in sql


# ── Pattern Engine: Most Used Category ──

class TestPatternMostUsedCategory:
    def test_most_used_category_this_month(self, engine):
        result = engine.match("Which category did I use the most this month?")
        assert result is not None
        sql, pname = result
        assert pname == "most_used_category"
        assert "GROUP BY category" in sql
        assert "ORDER BY count DESC LIMIT 1" in sql
        assert "date LIKE '2025-06%'" in sql


# ── Pattern Engine: Year to Date ──

class TestPatternYearToDate:
    def test_year_to_date(self, engine):
        result = engine.match("What is my year to date spending?")
        assert result is not None
        sql, pname = result
        assert pname == "year_to_date"
        assert "SUM(amount)" in sql
        assert "date LIKE '2025%'" in sql

    def test_this_year_so_far(self, engine):
        result = engine.match("What is my year to date spending")
        assert result is not None
        assert result[1] == "year_to_date"


# ── Pattern Engine: Most Recent ──

class TestPatternMostRecent:
    def test_most_recent_expense(self, engine):
        result = engine.match("What was my most recent expense?")
        assert result is not None
        sql, pname = result
        assert pname == "most_recent"
        assert "ORDER BY date DESC, id DESC LIMIT 1" in sql


# ── Pattern Engine: Description Spend ──

class TestPatternDescriptionSpend:
    def test_how_much_on_uber(self, engine):
        result = engine.match("How much did I spend on Uber this month?")
        assert result is not None
        sql, pname = result
        assert pname == "description_spend"
        assert "LOWER(description) LIKE '%uber%'" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_spent_on_pathao(self, engine):
        result = engine.match("How much on Pathao this month?")
        assert result is not None
        sql, pname = result
        assert pname == "description_spend"
        assert "LOWER(description) LIKE '%pathao%'" in sql


# ── Pattern Engine: Count by Category ──

class TestPatternCountByCategory:
    def test_count_by_category_this_month(self, engine):
        result = engine.match("Count expenses by category this month")
        assert result is not None
        sql, pname = result
        assert pname == "count_by_category"
        assert "GROUP BY category" in sql
        assert "COUNT(*) as count" in sql
        assert "date LIKE '2025-06%'" in sql

    def test_how_many_times_per_category(self, engine):
        result = engine.match("How many times did I spend per category this month?")
        assert result is not None
        assert result[1] == "count_by_category"


# ── Pattern Engine: Date Highest Spend ──

class TestPatternDateHighestSpend:
    def test_which_date_spent_most(self, engine):
        result = engine.match("How much on which date this month?")
        assert result is not None
        sql, pname = result
        assert pname == "date_highest_spend"
        assert "GROUP BY date" in sql
        assert "ORDER BY total DESC LIMIT 1" in sql
        assert "date LIKE '2025-06%'" in sql


# ── Pattern Engine: Budget ──

class TestPatternBudget:
    def test_budget_for_category(self, engine):
        result = engine.match("How much budget left for Groceries this month?")
        assert result is not None
        sql, pname = result
        assert pname == "budget"
        assert "budgets b" in sql
        assert "LEFT JOIN expenses e" in sql
        assert "category = 'Groceries'" in sql

    def test_overall_budget(self, engine):
        result = engine.match("Do I have budget left?")
        assert result is not None
        sql, pname = result
        assert pname == "budget"
        assert "__overall__" in sql

    def test_show_all_budgets(self, engine):
        result = engine.match("Show me all my budgets")
        assert result is not None
        sql, pname = result
        assert pname == "budgets_all"
        assert "LEFT JOIN" in sql
        assert "GROUP BY category" in sql


# ── Pattern Engine: Pacing ──

class TestPatternPacing:
    def test_on_track(self, engine):
        result = engine.match("Am I on track with my spending this month?")
        assert result is not None
        sql, pname = result
        assert pname == "pacing"
        assert "daily_avg" in sql
        assert "days_elapsed" in sql
        assert "days_in_month" in sql
        assert "date LIKE '2025-06%'" in sql


# ── Pattern Engine: Edge cases ──

class TestPatternEdgeCases:
    def test_empty_question(self, engine):
        assert engine.match("") is None

    def test_whitespace_question(self, engine):
        assert engine.match("   ") is None

    def test_non_expense_question(self, engine):
        assert engine.match("What is the weather today?") is None

    def test_greeting(self, engine):
        assert engine.match("Hello, how are you?") is None

    def test_question_about_budget_remaining(self, engine):
        result = engine.match("How much budget is remaining for Food?")
        assert result is not None
        assert result[1] == "budget"


# ── Apply All Fixes Pipeline (integration of fixers with real questions) ──

class TestFixerPipelineIntegration:
    def test_category_fix_added(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
        result = SqlService.apply_all_fixes(sql, "How much on Transport this month?")
        assert "category = 'Transport'" in result

    def test_category_fix_replaced(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND category = 'Food'"
        result = SqlService.apply_all_fixes(sql, "How much on Transport?")
        assert "category = 'Transport'" in result
        assert "category = 'Food'" not in result

    def test_aggregate_fix_applied(self):
        sql = "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = SqlService.apply_all_fixes(sql, "How much did I spend this month?")
        assert "SUM(amount)" in result
        assert "date, description" not in result

    def test_show_expenses_fix_applied(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = SqlService.apply_all_fixes(sql, "Show my expenses this month")
        assert "date, description, category, amount" in result or "id, date, description" in result

    def test_frequency_fix(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = SqlService.apply_all_fixes(sql, "How many times did I dine out this month?")
        assert "COUNT(*) as count" in result
        assert "SUM(amount)" not in result

    def test_most_expensive_fix(self):
        sql = "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = SqlService.apply_all_fixes(sql, "What was my most expensive expense this month?")
        assert "ORDER BY amount DESC LIMIT 1" in result

    def test_top_n_fix(self):
        sql = "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid LIMIT 50"
        result = SqlService.apply_all_fixes(sql, "Show top 3 expenses")
        assert "LIMIT 3" in result

    def test_budget_fix(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
        result = SqlService.apply_all_fixes(sql, "How much budget left for Groceries?")
        assert "budgets b" in result
        assert "LEFT JOIN" in result

    def test_descending_sort_fix(self):
        sql = "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid ORDER BY date"
        result = SqlService.apply_all_fixes(sql, "Show expenses descending by date")
        assert "DESC" in result.upper().split("ORDER BY")[1]

    def test_description_filter_fix(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = SqlService.apply_all_fixes(sql, "How much on Uber this month?")
        assert "LOWER(description) LIKE" in result

    def test_ordinal_fix(self):
        sql = "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid ORDER BY amount DESC LIMIT 50"
        result = SqlService.apply_all_fixes(sql, "Show the third transaction this month")
        assert "OFFSET 2" in result

    def test_category_breakdown_fix(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = SqlService.apply_all_fixes(sql, "Show category breakdown this month")
        assert "GROUP BY category" in result
        assert "SUM(amount)" in result

    def test_limit_syntax_fix(self):
        sql = "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid ORDER BY amount DESC LIMIT 5, 10"
        result = SqlService.apply_all_fixes(sql, "Show expenses")
        assert "LIMIT 10 OFFSET 5" in result


# ── Validate Results ──

class TestValidateResults:
    def test_no_issues_for_valid_result(self):
        questions = "How much did I spend on Food?"
        columns = ["total", "count"]
        rows = [{"total": 500.0, "count": 3}]
        issues = SqlService.validate_results(questions, columns, rows)
        assert issues == []

    def test_missing_amount_column(self):
        issues = SqlService.validate_results(
            "How much did I spend on Food?",
            ["category"],
            [{"category": "Food"}],
        )
        assert len(issues) > 0
        assert "amount" in issues[0]

    def test_category_mismatch(self):
        issues = SqlService.validate_results(
            "How much on Food?",
            ["category", "total"],
            [{"category": "Transport", "total": 100}],
        )
        assert len(issues) > 0
        assert "Transport" in issues[0]

    def test_list_intent_aggregate_result(self):
        issues = SqlService.validate_results(
            "Show me my Food expenses",
            ["total"],
            [{"total": 500}],
        )
        assert len(issues) > 0
        assert "aggregate" in issues[0]

    def test_empty_result_for_time_period(self):
        issues = SqlService.validate_results(
            "How much did I spend this month?",
            ["total"],
            [],
        )
        assert len(issues) > 0
        assert "empty" in issues[0]


# ── Pattern Engine: Amount Range (BETWEEN) ──

class TestPatternAmountRange:
    def test_between_range_list(self, engine):
        result = engine.match("Show expenses between 100 and 500 this month")
        assert result is not None
        sql, pname = result
        assert pname == "amount_range"
        assert "BETWEEN 100 AND 500" in sql
        assert "date, description, amount, category" in sql

    def test_between_range_aggregate(self, engine):
        result = engine.match("How much did I spend between 50 and 200 this month?")
        assert result is not None
        sql, pname = result
        assert pname == "amount_range"
        assert "BETWEEN" in sql
        assert "SUM(amount)" in sql

    def test_from_to_range(self, engine):
        result = engine.match("Expenses from 1000 to 5000?")
        assert result is not None
        sql, pname = result
        assert pname == "amount_range"
        assert "BETWEEN 1000 AND 5000" in sql


# ── Pattern Engine: Unused Categories ──

class TestPatternUnusedCategories:
    def test_unused_categories_this_month(self, engine):
        result = engine.match("Which categories did I not spend on this month?")
        assert result is not None
        sql, pname = result
        assert pname == "unused_categories"

    def test_no_spending_in_category(self, engine):
        result = engine.match("What categories have no expenses this month?")
        assert result is not None
        assert result[1] == "unused_categories"

    def test_without_time_no_match(self, engine):
        result = engine.match("What categories have no expenses?")
        assert result is None


# ── Pattern Engine: Category Comparison ──

class TestPatternCategoryComparison:
    def test_how_much_more_than(self, engine):
        result = engine.match("How much more on Food than Transport this month?")
        assert result is not None
        sql, pname = result
        assert pname == "category_comparison"
        assert "Food" in sql
        assert "Transport" in sql

    def test_more_on_than(self, engine):
        result = engine.match("Did I spend more on Groceries than Dining Out this month?")
        assert result is not None
        sql, pname = result
        assert pname == "category_comparison"


# ── Format Answer: Category Comparison ──

class TestFormatAnswerCategoryComparison:
    def test_category_comparison_format(self):
        from llm.qa import format_answer
        data = [
            {"category": "Food", "total": 5000.0},
            {"category": "Transport", "total": 2000.0},
        ]
        result = format_answer(["category", "total"], data, "How much more on Food than Transport?")
        assert "comparison" in result["type"]
        assert "৳5000" in result["text"]
        assert "৳2000" in result["text"]
        assert "৳3000" in result["text"]


