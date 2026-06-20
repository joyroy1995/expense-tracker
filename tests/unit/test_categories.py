import pytest
from llm.categories import (
    bengali_to_english_num,
    extract_amount_fallback,
    keyword_category,
    CATEGORIES,
    CATEGORY_KEYWORDS,
)


class TestBengaliToEnglishNum:
    def test_bengali_digits_converted(self):
        assert bengali_to_english_num("৫০") == "50"
        assert bengali_to_english_num("১২৩") == "123"
        assert bengali_to_english_num("০") == "0"

    def test_mixed_bengali_and_english(self):
        assert bengali_to_english_num("৫০ টাকা 30") == "50 টাকা 30"

    def test_no_bengali_digits(self):
        assert bengali_to_english_num("hello 123") == "hello 123"

    def test_empty_string(self):
        assert bengali_to_english_num("") == ""

    def test_all_bengali_digits(self):
        assert bengali_to_english_num("০১২৩৪৫৬৭৮৯") == "0123456789"


class TestExtractAmountFallback:
    def test_simple_number(self):
        assert extract_amount_fallback("khoroch korlam 500") == 500.0

    def test_with_taka_suffix(self):
        assert extract_amount_fallback("gorur mangsho 600 taka") == 600.0

    def test_with_tk_suffix(self):
        assert extract_amount_fallback("mach 300 tk") == 300.0

    def test_with_bengali_taka(self):
        assert extract_amount_fallback("ভাত ২০ টাকা") == 20.0

    def test_bengali_digits(self):
        assert extract_amount_fallback("৫০ টাকা") == 50.0

    def test_decimal_amount(self):
        assert extract_amount_fallback("khabar 45.50 tk") == 45.50

    def test_last_number_taken(self):
        assert extract_amount_fallback("gorur mangsho 600 ar mach 300, rickshaw 50") == 50.0

    def test_no_number_returns_none(self):
        assert extract_amount_fallback("khabar khelam") is None

    def test_empty_string(self):
        assert extract_amount_fallback("") is None

    def test_tk_character_removed(self):
        assert extract_amount_fallback("khabar 100৳") == 100.0

    def test_bengali_numeral_mixed(self):
        assert extract_amount_fallback("bazar ৫০০ টাকা") == 500.0


class TestKeywordCategory:
    def test_food_keyword(self):
        assert keyword_category("lunch khelam") == "Food"

    def test_transport_keyword(self):
        assert keyword_category("rickshaw te gelam") == "Transport"

    def test_shopping_keyword(self):
        assert keyword_category("daraz e jama kinlam") == "Shopping"

    def test_health_keyword(self):
        assert keyword_category("oshudh kinlam") == "Health"

    def test_education_keyword(self):
        assert keyword_category("boi kinlam") == "Education"

    def test_entertainment_keyword(self):
        assert keyword_category("movie ticket") == "Entertainment"

    def test_dining_out_keyword(self):
        assert keyword_category("restaurant e biryani") == "Dining Out"

    def test_fruits_keyword(self):
        assert keyword_category("aam kinlam") == "Fruits"

    def test_groceries_keyword(self):
        assert keyword_category("bazar korlam") == "Groceries"

    def test_travel_keyword(self):
        assert keyword_category("sajek tour") == "Travel"

    def test_personal_care_keyword(self):
        assert keyword_category("haircut korlam") == "Personal Care"

    def test_gifts_keyword(self):
        assert keyword_category("birthday gift") == "Gifts"

    def test_investment_keyword(self):
        assert keyword_category("share kinlam") == "Investment"

    def test_savings_keyword(self):
        assert keyword_category("dps deposit") == "Savings"

    def test_bills_keyword(self):
        assert keyword_category("electricity bill") == "Bills"

    def test_rent_keyword(self):
        assert keyword_category("bari bhara diyechi") == "Rent"

    def test_no_match_returns_other(self):
        assert keyword_category("random text with no keywords") == "Other"

    def test_empty_string_returns_other(self):
        assert keyword_category("") == "Other"

    def test_case_insensitive(self):
        assert keyword_category("LUNCH KHELAM") == "Food"

    def test_first_keyword_match_wins(self):
        assert keyword_category("restaurant biryani") == "Dining Out"

    def test_bengali_text(self):
        assert keyword_category("khabar kheyechi") == "Food"

    def test_keyword_at_start_of_word(self):
        result = keyword_category("hotelier somossa")
        assert result != "Food"
