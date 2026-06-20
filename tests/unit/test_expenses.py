import pytest
from datetime import date, timedelta
from llm.expenses import extract_keywords, check_learned, clean_date_refs, extract_date_reference


class TestExtractKeywords:
    def test_basic_keywords(self):
        result = extract_keywords("lunch khelam 500")
        assert "lunch" in result
        assert "khelam" in result
        assert "500" not in result

    def test_filters_short_words(self):
        result = extract_keywords("a an is at")
        assert "a" not in result
        assert all(len(w) >= 2 for w in result)

    def test_filters_exclude_keywords(self):
        result = extract_keywords("taka tk bdt")
        assert result == []

    def test_removes_punctuation(self):
        result = extract_keywords("hello, world!")
        assert "hello" in result
        assert "world" in result

    def test_mixed_bengali_english(self):
        result = extract_keywords("gorur mangsho 600 tk")
        assert "gorur" in result
        assert "mangsho" in result
        assert "600" not in result
        assert "tk" not in result

    def test_empty_string(self):
        assert extract_keywords("") == []

    def test_only_digits(self):
        assert extract_keywords("500 600 700") == []


class TestCheckLearned:
    SEED_ONLY = None

    def test_seed_category_match(self):
        result = check_learned("chira kinlam", self.SEED_ONLY)
        assert result == "Groceries"

    def test_seed_fruit_match(self):
        result = check_learned("aam kinlam", self.SEED_ONLY)
        assert result == "Fruits"

    def test_seed_transport_match(self):
        result = check_learned("rickshaw te gelam", self.SEED_ONLY)
        assert result == "Transport"

    def test_seed_dining_out(self):
        result = check_learned("kacchi khelam", self.SEED_ONLY)
        assert result == "Dining Out"

    def test_no_match_returns_none(self):
        result = check_learned("random unknown word", self.SEED_ONLY)
        assert result is None

    def test_learned_dict_overrides_seed(self):
        learned = {"chira": "Food"}
        result = check_learned("chira kinlam", learned)
        assert result == "Food"

    def test_learned_dict_new_match(self):
        learned = {"customitem": "Shopping"}
        result = check_learned("customitem kinlam", learned)
        assert result == "Shopping"

    def test_empty_description(self):
        result = check_learned("", self.SEED_ONLY)
        assert result is None

    def test_learned_dict_empty(self):
        result = check_learned("chira kinlam", {})
        assert result == "Groceries"


class TestCleanDateRefs:
    def test_removes_yesterday(self):
        assert clean_date_refs("yesterday khabar") == "khabar"

    def test_removes_today(self):
        assert clean_date_refs("today lunch") == "lunch"

    def test_removes_tomorrow(self):
        assert clean_date_refs("tomorrow plan") == "plan"

    def test_removes_last_week(self):
        assert clean_date_refs("last week expenses") == "expenses"

    def test_removes_last_month(self):
        assert clean_date_refs("last month total") == "total"

    def test_removes_ago_phrases(self):
        assert clean_date_refs("3 days ago khabar") == "khabar"

    def test_removes_bengali_dates(self):
        assert clean_date_refs("গতকাল khabar") == "khabar"

    def test_removes_weekday_names(self):
        assert clean_date_refs("monday khabar") == "khabar"

    def test_removes_multiple_date_refs(self):
        result = clean_date_refs("yesterday last month")
        assert result == ""

    def test_empty_string(self):
        assert clean_date_refs("") == ""

    def test_no_date_ref_preserved(self):
        assert clean_date_refs("gorur mangsho 600 tk") == "gorur mangsho 600 tk"

    def test_removes_kalke(self):
        assert clean_date_refs("kalke khabar") == "khabar"

    def test_removes_parshu(self):
        assert clean_date_refs("parshu khabar") == "khabar"

    def test_removes_couple_of_days(self):
        assert clean_date_refs("couple of days ago khabar") == "khabar"

    def test_removes_few_days_ago(self):
        assert clean_date_refs("few days ago khabar") == "khabar"

    def test_removes_this_morning(self):
        assert clean_date_refs("this morning khabar") == "khabar"

    def test_removes_month_name_date(self):
        assert clean_date_refs("january 15 khabar") == "khabar"

    def test_removes_numeric_date(self):
        assert clean_date_refs("2024-01-15 khabar") == "khabar"

    def test_removes_bangla_phrases(self):
        assert clean_date_refs("গত সপ্তাহে khabar") == "khabar"
        assert clean_date_refs("এই মাসে khabar") == "khabar"


class TestExtractDateReference:
    @pytest.fixture
    def now(self):
        return date(2025, 6, 15)

    def test_today(self, now):
        result, ref = extract_date_reference("today khabar", now)
        assert ref == "2025-06-15"

    def test_yesterday(self, now):
        result, ref = extract_date_reference("yesterday khabar", now)
        assert ref == "2025-06-14"

    def test_parshu_day_before_yesterday(self, now):
        result, ref = extract_date_reference("parshu khabar", now)
        assert ref == "2025-06-13"

    def test_3_days_ago(self, now):
        result, ref = extract_date_reference("3 days ago khabar", now)
        assert ref == "2025-06-12"

    def test_koyekdin_age(self, now):
        result, ref = extract_date_reference("koyekdin age khabar", now)
        assert ref == "2025-06-13"

    def test_last_week(self, now):
        result, ref = extract_date_reference("last week khabar", now)
        assert ref == "2025-06-08"

    def test_previous_week(self, now):
        result, ref = extract_date_reference("previous week khabar", now)
        assert ref == "2025-06-08"

    def test_this_week(self, now):
        result, ref = extract_date_reference("this week spending", now)
        # June 15, 2025 is a Sunday (weekday() == 6)
        # Monday = 0, so shift = (6 - 0) % 7 = 6, so June 9
        monday = now - timedelta(days=now.weekday())
        assert ref == monday.strftime("%Y-%m-%d")

    def test_last_month(self, now):
        result, ref = extract_date_reference("last month total", now)
        assert ref == "2025-05-15"

    def test_previous_month(self, now):
        result, ref = extract_date_reference("previous month total", now)
        assert ref == "2025-05-15"

    def test_a_week_ago(self, now):
        result, ref = extract_date_reference("a week ago khabar", now)
        assert ref == "2025-06-08"

    def test_a_month_ago(self, now):
        result, ref = extract_date_reference("a month ago khabar", now)
        assert ref == "2025-05-15"

    def test_this_month(self, now):
        result, ref = extract_date_reference("this month spending", now)
        assert ref == "2025-06-01"

    def test_no_date_reference(self, now):
        result, ref = extract_date_reference("gorur mangsho 600 tk", now)
        assert ref == "2025-06-15"

    def test_compare_keyword_returns_empty(self, now):
        result, ref = extract_date_reference("compare to last month", now)
        assert ref == ""

    def test_exact_iso_date(self, now):
        result, ref = extract_date_reference("on 2025-05-10 khabar", now)
        assert ref == "2025-05-10"

    def test_bengali_cal(self, now):
        result, ref = extract_date_reference("গতকাল khabar", now)
        assert ref == "2025-06-14"

    def test_empty_text(self, now):
        result, ref = extract_date_reference("", now)
        assert ref == "2025-06-15"

    def test_tarikh_pattern(self, now):
        result, ref = extract_date_reference("10 tarikhe khabar", now)
        assert ref in ("2025-06-10", "2025-05-10")

    def test_weekday_name_last(self, now):
        # June 15, 2025 is Sunday (weekday 6)
        # "last friday" → Friday is weekday 4, days_ago = (6-4) = 2, but since prefix is "last", if same day -> 7
        # Actually days_ago = (6 - 4) % 7 = 2, prefix is last, and 2 != 0 so days_ago stays 2
        # So last friday from Sunday = June 13
        result, ref = extract_date_reference("last friday khabar", now)
        expected = (now - timedelta(days=(now.weekday() - 4) % 7)).strftime("%Y-%m-%d")
        assert ref == expected

    def test_month_before_last(self, now):
        result, ref = extract_date_reference("the month before last", now)
        assert ref == "2025-05-01"

    def test_week_before_last(self, now):
        result, ref = extract_date_reference("the week before last", now)
        assert ref == "2025-06-01"

    def test_couple_of_days_ago(self, now):
        result, ref = extract_date_reference("a couple of days ago khabar", now)
        assert ref == "2025-06-13"

    def test_few_days_ago(self, now):
        result, ref = extract_date_reference("a few days ago khabar", now)
        assert ref == "2025-06-12"

    def test_has_date_method(self):
        from datetime import datetime
        now_dt = datetime(2025, 6, 15, 10, 30, 0)
        result, ref = extract_date_reference("yesterday khabar", now_dt)
        assert ref == "2025-06-14"

    def test_this_morning(self, now):
        result, ref = extract_date_reference("this morning khabar", now)
        assert ref == "2025-06-15"

    def test_kalke_pattern(self, now):
        result, ref = extract_date_reference("kalke khabar", now)
        assert ref == "2025-06-14"
