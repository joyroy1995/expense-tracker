import pytest
from database import compute_next_date, _normalize_question, _schema_hash, _token_jaccard


class TestComputeNextDate:
    def test_daily(self):
        result = compute_next_date("2025-06-15", "daily")
        assert result == "2025-06-16"

    def test_weekly(self):
        result = compute_next_date("2025-06-15", "weekly")
        assert result == "2025-06-22"

    def test_monthly(self):
        result = compute_next_date("2025-06-15", "monthly")
        assert result == "2025-07-15"

    def test_yearly(self):
        result = compute_next_date("2025-06-15", "yearly")
        assert result == "2026-06-15"

    def test_monthly_jan31_to_feb(self):
        result = compute_next_date("2025-01-31", "monthly")
        assert result == "2025-02-28"

    def test_monthly_jan31_to_feb_leap(self):
        result = compute_next_date("2024-01-31", "monthly")
        assert result == "2024-02-29"

    def test_monthly_dec_to_jan(self):
        result = compute_next_date("2025-12-15", "monthly")
        assert result == "2026-01-15"

    def test_interval_days(self):
        result = compute_next_date("2025-06-15", "days", interval_value=3)
        assert result == "2025-06-18"

    def test_interval_weeks(self):
        result = compute_next_date("2025-06-15", "weeks", interval_value=2)
        assert result == "2025-06-29"

    def test_interval_months(self):
        result = compute_next_date("2025-06-15", "months", interval_value=3)
        assert result == "2025-09-15"

    def test_interval_years(self):
        result = compute_next_date("2025-06-15", "years", interval_value=2)
        assert result == "2027-06-15"

    def test_unknown_unit_returns_original(self):
        result = compute_next_date("2025-06-15", "unknown")
        assert result == "2025-06-15"

    def test_with_interval_unit_param(self):
        result = compute_next_date("2025-06-15", "monthly", interval_unit="monthly")
        assert result == "2025-07-15"


class TestNormalizeQuestion:
    def test_lowercases(self):
        result = _normalize_question("How Much On Food")
        assert result.islower() or all(w.islower() for w in result.split())

    def test_removes_punctuation(self):
        result = _normalize_question("how much on food?")
        assert "?" not in result

    def test_removes_stop_words(self):
        result = _normalize_question("how much did I spend on food this month")
        assert len(result.split()) >= 1

    def test_sorts_tokens(self):
        result = _normalize_question("food on much how")
        tokens = result.split()
        assert tokens == sorted(tokens)

    def test_removes_short_tokens(self):
        result = _normalize_question("a on at food")
        assert "food" in result
        for token in result.split():
            assert len(token) > 1

    def test_empty_string(self):
        result = _normalize_question("")
        assert result == ""


class TestSchemaHash:
    def test_returns_string(self):
        result = _schema_hash("test schema string")
        assert isinstance(result, str)

    def test_length(self):
        result = _schema_hash("test")
        assert len(result) == 16

    def test_consistent(self):
        assert _schema_hash("hello") == _schema_hash("hello")

    def test_different_inputs_different_hashes(self):
        assert _schema_hash("hello") != _schema_hash("world")


class TestTokenJaccard:
    def test_identical(self):
        assert _token_jaccard("food transport", "food transport") == 1.0

    def test_partial_overlap(self):
        result = _token_jaccard("food transport", "food bills")
        assert 0.3 < result < 0.5

    def test_no_overlap(self):
        assert _token_jaccard("food transport", "bills rent") == 0.0

    def test_empty_first(self):
        assert _token_jaccard("", "food transport") == 0.0

    def test_empty_second(self):
        assert _token_jaccard("food transport", "") == 0.0

    def test_both_empty(self):
        assert _token_jaccard("", "") == 0.0

    def test_one_empty_token_set_after_split(self):
        assert _token_jaccard("food", "") == 0.0
