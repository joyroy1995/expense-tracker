import pytest
from llm.budget import detect_budget_intent


class TestDetectBudgetIntent:
    def test_overall_budget_set(self):
        result = detect_budget_intent("monthly budget 5000")
        assert result == {"category": "__overall__", "amount": 5000.0}

    def test_overall_budget_banglish(self):
        result = detect_budget_intent("monthly budget set koro 10000")
        assert result == {"category": "__overall__", "amount": 10000.0}

    def test_overall_budget_with_maximum(self):
        result = detect_budget_intent("maximum spending limit hobe 30000")
        assert result == {"category": "__overall__", "amount": 30000.0}

    def test_category_specific_budget(self):
        result = detect_budget_intent("food budget 5000")
        assert result == {"category": "Food", "amount": 5000.0}

    def test_category_budget(self):
        result = detect_budget_intent("food er budget set koro 5000")
        assert result is not None and result["category"] == "Food"

    def test_category_budget_with_set_and_of(self):
        result = detect_budget_intent("set budget for transport 3000")
        assert result == {"category": "Transport", "amount": 3000.0}

    def test_category_budget_is_pattern(self):
        result = detect_budget_intent("budget for food is 4000")
        assert result == {"category": "Food", "amount": 4000.0}

    def test_category_budget_hobe_pattern(self):
        result = detect_budget_intent("transport budget hobe 2500")
        assert result == {"category": "Transport", "amount": 2500.0}

    def test_no_budget_intent(self):
        assert detect_budget_intent("how much did I spend on food") is None

    def test_empty_string_returns_none(self):
        assert detect_budget_intent("") is None

    def test_none_input_returns_none(self):
        assert detect_budget_intent(None) is None

    def test_whitespace_only(self):
        assert detect_budget_intent("   ") is None

    def test_dining_out_category(self):
        result = detect_budget_intent("dining out budget 8000")
        assert result == {"category": "Dining Out", "amount": 8000.0}

    def test_bills_budget(self):
        result = detect_budget_intent("bills er budget set koro 5000")
        assert result == {"category": "Bills", "amount": 5000.0}

    def test_groceries_budget_with_diben(self):
        result = detect_budget_intent("groceries budget diben 12000")
        assert result == {"category": "Groceries", "amount": 12000.0}

    def test_entertainment_budget_with_hole(self):
        result = detect_budget_intent("entertainment budget hole 2000")
        assert result == {"category": "Entertainment", "amount": 2000.0}

    def test_decimal_amount(self):
        result = detect_budget_intent("food budget 1500.50")
        assert result == {"category": "Food", "amount": 1500.50}

    def test_add_new_budget(self):
        result = detect_budget_intent("add new monthly budget 7000")
        assert result is not None and result["category"] == "__overall__"

    def test_ekhon_budget(self):
        result = detect_budget_intent("ekhon budget set koro 8000")
        assert result is not None and result["category"] == "__overall__"

    def test_amr_budget(self):
        result = detect_budget_intent("amr monthly budget set koro 15000")
        assert result is not None and result["category"] == "__overall__"

    def test_personal_care_budget(self):
        result = detect_budget_intent("personal care budget 1000")
        assert result == {"category": "Personal Care", "amount": 1000.0}
