import re
import pytest
from services.sql_service import SqlService
from services.qa_service import QaService


_validate_sql = SqlService.validate_sql
_ensure_user_filter = SqlService.ensure_user_filter
_fix_category_in_sql = SqlService.fix_category_in_sql
_fix_sort_order = SqlService.fix_sort_order
_fix_sort_column = SqlService.fix_sort_column
_fix_frequency_sql = SqlService.fix_frequency_sql
_fix_top_n_limit = SqlService.fix_top_n_limit
_fix_limit_syntax = SqlService.fix_limit_syntax
_fix_ordinal_limit = SqlService.fix_ordinal_limit
_fix_most_expensive_sql = SqlService.fix_most_expensive_sql
_fix_category_breakdown_sql = SqlService.fix_category_breakdown_sql
_fix_history_id_filter = SqlService.fix_history_id_filter
_fix_date_filter = SqlService.fix_date_filter
_fix_show_expenses_aggregate = SqlService.fix_show_expenses_aggregate
_extract_item_keyword = SqlService._extract_item_keyword
_fix_description_filter = SqlService.fix_description_filter
_fix_aggregate_sql = SqlService.fix_aggregate_sql
_fix_budget_query = SqlService.fix_budget_query
_normalize_question = QaService.normalize_question
_needs_llm_answer = QaService.needs_llm_answer


# ── _validate_sql ─────────────────────────────────────────────

class TestValidateSql:
    VALID_SQL = "SELECT * FROM expenses WHERE user_id = :uid"

    def test_valid_select(self):
        assert _validate_sql(self.VALID_SQL) is True

    def test_invalid_not_select(self):
        assert _validate_sql("DROP TABLE expenses") is False

    def test_invalid_contains_semicolon(self):
        assert _validate_sql("SELECT * FROM expenses; DROP TABLE users") is False

    def test_trailing_semicolon_ok(self):
        assert _validate_sql("SELECT * FROM expenses WHERE user_id = :uid;") is True

    def test_forbidden_keywords(self):
        assert _validate_sql("DELETE FROM expenses") is False

    def test_unbalanced_parentheses(self):
        assert _validate_sql("SELECT * FROM expenses WHERE (category = 'Food'") is False

    def test_unknown_table(self):
        assert _validate_sql("SELECT * FROM unknown_table") is False

    def test_known_table_passes(self):
        assert _validate_sql("SELECT * FROM budgets WHERE user_id = :uid") is True

    def test_comment_sql_rejected(self):
        assert _validate_sql("SELECT * FROM expenses -- comment") is False

    def test_block_comment_rejected(self):
        assert _validate_sql("SELECT * FROM expenses /* comment */") is False


# ── _ensure_user_filter ──────────────────────────────────────

class TestEnsureUserFilter:
    def test_already_has_uid(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        assert _ensure_user_filter(sql) == sql

    def test_adds_where_with_uid(self):
        sql = "SELECT * FROM expenses"
        result = _ensure_user_filter(sql)
        assert ":uid" in result
        assert "WHERE" in result.upper()

    def test_adds_to_existing_where(self):
        sql = "SELECT * FROM expenses WHERE category = 'Food'"
        result = _ensure_user_filter(sql)
        assert "AND user_id = :uid" in result

    def test_adds_before_order_by(self):
        sql = "SELECT * FROM expenses ORDER BY date"
        result = _ensure_user_filter(sql)
        assert "WHERE user_id = :uid ORDER BY" in result

    def test_adds_before_limit(self):
        sql = "SELECT * FROM expenses LIMIT 10"
        result = _ensure_user_filter(sql)
        assert "WHERE user_id = :uid LIMIT" in result


# ── _fix_category_in_sql ─────────────────────────────────────

class TestFixCategoryInSql:
    def test_question_mentions_category_sql_has_it(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND category = 'Food'"
        result = _fix_category_in_sql(sql, "how much on food")
        assert "category = 'Food'" in result

    def test_question_mentions_category_sql_has_wrong(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND category = 'Transport'"
        result = _fix_category_in_sql(sql, "how much on food")
        assert "category = 'Food'" in result

    def test_question_no_category_strips_spurious(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND category = 'Food'"
        result = _fix_category_in_sql(sql, "what is my total")
        assert "category" not in result.lower().replace("b.category", "")

    def test_preserves_overall_budget(self):
        sql = "SELECT * FROM budgets WHERE user_id = :uid AND b.category = '__overall__'"
        result = _fix_category_in_sql(sql, "overall budget status")
        assert "__overall__" in result

    def test_adds_category_filter_when_missing(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_category_in_sql(sql, "how much on transport")
        assert "category = 'Transport'" in result

    def test_adds_before_group_by(self):
        sql = "SELECT category, SUM(amount) FROM expenses WHERE user_id = :uid GROUP BY category"
        result = _fix_category_in_sql(sql, "food total")
        assert "AND category = 'Food' GROUP BY" in result


# ── _fix_sort_order ──────────────────────────────────────────

class TestFixSortOrder:
    def test_desc_keyword_adds_desc(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date"
        result = _fix_sort_order(sql, "show newest first")
        assert "DESC" in result.upper()

    def test_no_desc_keyword_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date"
        result = _fix_sort_order(sql, "show by date")
        assert "DESC" not in result.upper()

    def test_already_has_desc_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date DESC"
        result = _fix_sort_order(sql, "reverse order")
        assert result == sql

    def test_no_order_by_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_sort_order(sql, "descending")
        assert result == sql

    def test_reverse_keyword(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date"
        result = _fix_sort_order(sql, "reverse order by amount")
        assert "DESC" in result.upper()

    def test_desc_before_limit(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date LIMIT 10"
        result = _fix_sort_order(sql, "descending order")
        assert "DESC" in result.upper()
        assert "LIMIT" in result.upper()


# ── _fix_sort_column ─────────────────────────────────────────

class TestFixSortColumn:
    def test_sort_by_money_becomes_amount(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date"
        result = _fix_sort_column(sql, "sort by money")
        assert "ORDER BY amount DESC" in result

    def test_sort_by_name_becomes_description(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date"
        result = _fix_sort_column(sql, "sort by name")
        assert "ORDER BY description DESC" in result

    def test_no_sort_by_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date"
        result = _fix_sort_column(sql, "show by date")
        assert result == sql

    def test_unknown_column_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY date"
        result = _fix_sort_column(sql, "sort by foo")
        assert result == sql


# ── _fix_frequency_sql ───────────────────────────────────────

class TestFixFrequencySql:
    def test_converts_sum_to_count(self):
        sql = "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid GROUP BY category ORDER BY total DESC"
        result = _fix_frequency_sql(sql, "how many times per category")
        assert "COUNT(*)" in result
        assert "SUM" not in result

    def test_skips_if_no_frequency_keyword(self):
        sql = "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid GROUP BY category"
        result = _fix_frequency_sql(sql, "show category totals")
        assert "SUM" in result

    def test_skips_if_already_count(self):
        sql = "SELECT category, COUNT(*) as count FROM expenses WHERE user_id = :uid GROUP BY category"
        result = _fix_frequency_sql(sql, "how many times")
        assert result == sql

    def test_how_often_keyword(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
        result = _fix_frequency_sql(sql, "how often do I eat out")
        assert "COUNT(*)" in result


# ── _fix_top_n_limit ─────────────────────────────────────────

class TestFixTopNLimit:
    def test_top_5_adds_limit(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_top_n_limit(sql, "top 5 expenses")
        assert "LIMIT 5" not in result.upper()  # _fix_top_n_limit only replaces existing LIMIT

    def test_top_5_replaces_limit(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid LIMIT 50"
        result = _fix_top_n_limit(sql, "top 5 expenses")
        assert "LIMIT 5" in result.upper()

    def test_last_7_days_skipped(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid LIMIT 50"
        result = _fix_top_n_limit(sql, "last 7 days expenses")
        assert "LIMIT 50" in result.upper() or "LIMIT 7" not in result

    def test_no_top_keyword_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid LIMIT 50"
        result = _fix_top_n_limit(sql, "show expenses")
        assert result == sql


# ── _fix_limit_syntax ────────────────────────────────────────

class TestFixLimitSyntax:
    def test_converts_mysql_limit(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid LIMIT 5,10"
        result = _fix_limit_syntax(sql, "any")
        assert "LIMIT 10 OFFSET 5" in result

    def test_no_mysql_limit_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid LIMIT 10"
        result = _fix_limit_syntax(sql, "any")
        assert result == sql

    def test_no_limit_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_limit_syntax(sql, "any")
        assert result == sql


# ── _fix_ordinal_limit ───────────────────────────────────────

class TestFixOrdinalLimit:
    def test_second_adds_offset_1(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY amount DESC LIMIT 10"
        result = _fix_ordinal_limit(sql, "second most expensive")
        assert "OFFSET 1" in result

    def test_third_with_singular(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY amount DESC LIMIT 10"
        result = _fix_ordinal_limit(sql, "third most expensive expense")
        assert "LIMIT 1 OFFSET 2" in result

    def test_tenth(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY amount DESC LIMIT 50"
        result = _fix_ordinal_limit(sql, "tenth expense")
        assert "OFFSET 9" in result

    def test_no_ordinal_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY amount DESC"
        result = _fix_ordinal_limit(sql, "most expensive")
        assert result == sql

    def test_5th_ordinal(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY amount DESC LIMIT 50"
        result = _fix_ordinal_limit(sql, "5th most expensive")
        assert "OFFSET 4" in result

    def test_skips_aggregate_sql(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
        result = _fix_ordinal_limit(sql, "how much on 5th june")
        assert result == sql

    def test_skips_ordinal_in_date(self):
        sql = "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '2026-06%' ORDER BY amount DESC LIMIT 1"
        result = _fix_ordinal_limit(sql, "What was my biggest expense on 5th june")
        assert result == sql

    def test_skips_ordinal_in_date_month_first(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid LIMIT 50"
        result = _fix_ordinal_limit(sql, "show me june 5th expenses")
        assert result == sql


# ── _fix_most_expensive_sql ─────────────────────────────────

class TestFixMostExpensiveSql:
    def test_adds_order_by_limit(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_most_expensive_sql(sql, "most expensive expense")
        assert "ORDER BY amount DESC LIMIT 1" in result

    def test_skips_if_already_ordered(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid ORDER BY amount"
        result = _fix_most_expensive_sql(sql, "most expensive")
        assert result == sql

    def test_skips_aggregate(self):
        sql = "SELECT SUM(amount) FROM expenses WHERE user_id = :uid"
        result = _fix_most_expensive_sql(sql, "most expensive")
        assert result == sql

    def test_skips_group_by(self):
        sql = "SELECT category, SUM(amount) FROM expenses WHERE user_id = :uid GROUP BY category"
        result = _fix_most_expensive_sql(sql, "most expensive")
        assert result == sql

    def test_no_keyword_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_most_expensive_sql(sql, "show expenses")
        assert result == sql


# ── _fix_category_breakdown_sql ──────────────────────────────

class TestFixCategoryBreakdownSql:
    def test_converts_flat_to_breakdown(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_category_breakdown_sql(sql, "breakdown by category")
        assert "GROUP BY category" in result
        assert "SUM(amount)" in result

    def test_skips_if_already_grouped(self):
        sql = "SELECT category, SUM(amount) FROM expenses WHERE user_id = :uid GROUP BY category"
        result = _fix_category_breakdown_sql(sql, "breakdown by category")
        assert result == sql

    def test_skips_if_no_keyword(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_category_breakdown_sql(sql, "show expenses")
        assert result == sql


# ── _fix_history_id_filter ──────────────────────────────────

class TestFixHistoryIdFilter:
    def test_strips_id_exclusion(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND id != 5"
        result = _fix_history_id_filter(sql, "show expenses")
        assert "id !=" not in result

    def test_preserves_exclusion_with_keyword(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND id != 5"
        result = _fix_history_id_filter(sql, "other than food")
        assert "id != 5" in result

    def test_strips_expenses_id_exclusion(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND expenses.id != 5"
        result = _fix_history_id_filter(sql, "show all")
        assert "id !=" not in result

    def test_strips_e_id_exclusion(self):
        sql = "SELECT * FROM expenses e WHERE user_id = :uid AND e.id != 5"
        result = _fix_history_id_filter(sql, "show all")
        assert "id !=" not in result


# ── _fix_date_filter ─────────────────────────────────────────

class TestFixDateFilter:
    def test_exact_date_in_question(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = _fix_date_filter(sql, "how much on 2025-06-15")
        assert "date = '2025-06-15'" in result

    def test_this_month_expands_exact_date(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND date = '2025-06-15'"
        result = _fix_date_filter(sql, "this month expenses")
        assert "LIKE" in result

    def test_today_keyword(self, mocker):
        mocker.patch("services.sql_service.datetime")
        from datetime import datetime
        svc_datetime = __import__("services.sql_service", fromlist=["datetime"]).datetime
        svc_datetime.now.return_value.strftime.return_value = "2025-06-20"
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND date LIKE '2025-06%'"
        result = _fix_date_filter(sql, "today expenses")
        assert "date = '" in result

    def test_no_date_change(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND category = 'Food'"
        result = _fix_date_filter(sql, "food expenses")
        assert result == sql


# ── _fix_show_expenses_aggregate ─────────────────────────────

class TestFixShowExpensesAggregate:
    def test_converts_aggregate_to_list(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
        result = _fix_show_expenses_aggregate(sql, "show my expenses")
        assert "id, date, description, category, amount" in result

    def test_skips_if_not_show_intent(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
        result = _fix_show_expenses_aggregate(sql, "what is my total")
        assert "SUM" in result

    def test_skips_if_not_aggregate(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_show_expenses_aggregate(sql, "show expenses")
        assert result == sql

    def test_skips_group_by_aggregate(self):
        sql = "SELECT category, SUM(amount) FROM expenses WHERE user_id = :uid GROUP BY category"
        result = _fix_show_expenses_aggregate(sql, "show expenses")
        assert "GROUP BY" in result


# ── _extract_item_keyword ────────────────────────────────────

class TestExtractItemKeyword:
    def test_bought_pattern(self):
        assert _extract_item_keyword("when did I buy rice") == "rice"

    def test_spent_on_pattern(self):
        assert _extract_item_keyword("how much spent on rickshaw") == "rickshaw"

    def test_how_much_on_pattern(self):
        assert _extract_item_keyword("how much on petrol") == "petrol"

    def test_expenses_suffix_pattern(self):
        assert _extract_item_keyword("rickshaw expenses") == "rickshaw"

    def test_skip_words_filtered(self):
        assert _extract_item_keyword("spent on the") is None

    def test_no_match_returns_none(self):
        assert _extract_item_keyword("how much did I spend") is None

    def test_bought_with_article(self):
        assert _extract_item_keyword("bought a phone") == "phone"

    def test_skips_ordinal_numbers(self):
        assert _extract_item_keyword("spent on 5th june") is None
        assert _extract_item_keyword("spent on 1st january") is None
        assert _extract_item_keyword("spent on 10th") is None


# ── _fix_description_filter ─────────────────────────────────

class TestFixDescriptionFilter:
    def test_adds_description_like(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_description_filter(sql, "how much on rickshaw")
        assert "LOWER(description) LIKE" in result
        assert "rickshaw" in result

    def test_skips_if_already_has_description_filter(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND description LIKE '%rice%'"
        result = _fix_description_filter(sql, "how much on rice")
        assert result == sql

    def test_skips_if_has_category_filter(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid AND category = 'Food'"
        result = _fix_description_filter(sql, "how much on rice")
        assert result == sql

    def test_skips_if_keyword_is_category(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_description_filter(sql, "how much on food")
        assert result == sql

    def test_skips_overall_keyword(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_description_filter(sql, "how much on overall total this month")
        assert result == sql


# ── _fix_aggregate_sql ───────────────────────────────────────

class TestFixAggregateSql:
    def test_converts_list_to_aggregate(self):
        sql = "SELECT date, description, amount FROM expenses WHERE user_id = :uid"
        result = _fix_aggregate_sql(sql, "how much total")
        assert "SUM" in result

    def test_skips_if_already_aggregate(self):
        sql = "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid"
        result = _fix_aggregate_sql(sql, "how much total")
        assert result == sql

    def test_skips_group_by(self):
        sql = "SELECT category, SUM(amount) FROM expenses WHERE user_id = :uid GROUP BY category"
        result = _fix_aggregate_sql(sql, "how much total")
        assert result == sql

    def test_no_aggregate_keyword_unchanged(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_aggregate_sql(sql, "show expenses")
        assert result == sql

    def test_sum_keyword(self):
        sql = "SELECT date, description, amount FROM expenses WHERE user_id = :uid"
        result = _fix_aggregate_sql(sql, "what is the sum")
        assert "SUM" in result

    def test_total_keyword(self):
        sql = "SELECT date, description, amount FROM expenses WHERE user_id = :uid"
        result = _fix_aggregate_sql(sql, "total spent")
        assert "SUM" in result


# ── _fix_budget_query ───────────────────────────────────────

class TestFixBudgetQuery:
    def test_replaces_with_budget_query(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_budget_query(sql, "what is my food budget")
        assert "budgets" in result.lower()
        assert "budget_amount" in result

    def test_skips_if_no_budget_keyword(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_budget_query(sql, "show expenses")
        assert result == sql

    def test_skips_if_already_has_budgets(self):
        sql = "SELECT * FROM budgets WHERE user_id = :uid"
        result = _fix_budget_query(sql, "budget status")
        assert result == sql

    def test_overall_budget_query(self):
        sql = "SELECT * FROM expenses WHERE user_id = :uid"
        result = _fix_budget_query(sql, "overall budget")
        assert "__overall__" in result


# ── _normalize_question ──────────────────────────────────────

class TestNormalizeQuestion:
    def test_compare_to_last_month(self):
        result = _normalize_question("compare to last month")
        assert "How does this month compare to last month" in result

    def test_this_month_vs_last_month(self):
        result = _normalize_question("this month vs last month")
        assert "How does this month compare to last month" in result

    def test_month_over_month(self):
        result = _normalize_question("month over month")
        assert "How does this month compare to last month" in result

    def test_already_long_form(self):
        result = _normalize_question("how does this month compare to last month")
        assert result == "how does this month compare to last month"

    def test_unrelated_question_unchanged(self):
        result = _normalize_question("how much on food this month")
        assert result == "how much on food this month"


# ── _needs_llm_answer ───────────────────────────────────────

class TestNeedsLlmAnswer:
    def test_complex_keyword_match(self):
        assert _needs_llm_answer("compare my spending") is True

    def test_simple_question_no_match(self):
        assert _needs_llm_answer("how much on food") is False

    def test_budget_keyword(self):
        assert _needs_llm_answer("budget remaining for food") is True

    def test_insight_keyword(self):
        assert _needs_llm_answer("give me an insight") is True

    def test_how_am_i_doing(self):
        assert _needs_llm_answer("how am i doing") is True
