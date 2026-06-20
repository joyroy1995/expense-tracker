import pytest
from export_service import _month_name, generate_csv, generate_xlsx, generate_pdf


class TestMonthName:
    def test_january(self):
        assert _month_name(1) == "January"

    def test_december(self):
        assert _month_name(12) == "December"

    def test_out_of_range_low(self):
        assert _month_name(0) == ""

    def test_out_of_range_high(self):
        assert _month_name(13) == ""


class TestGenerateCSV:
    def test_basic_csv(self):
        expenses = [
            {"date": "2025-06-15", "description": "lunch", "category": "Food", "amount": 350.0},
            {"date": "2025-06-15", "description": "bus", "category": "Transport", "amount": 30.0},
        ]
        result = generate_csv(expenses, 2025, 6)
        assert "Date,Description,Category,Amount" in result
        assert "lunch" in result
        assert "bus" in result
        assert "Total" in result
        assert "380.00" in result

    def test_empty_expenses(self):
        result = generate_csv([], 2025, 6)
        assert "Date,Description,Category,Amount" in result
        assert "Total" in result
        assert "0.00" in result

    def test_single_expense(self):
        expenses = [{"date": "2025-06-15", "description": "test", "category": "Other", "amount": 100.0}]
        result = generate_csv(expenses, 2025, 6)
        assert "test" in result
        assert "100.00" in result
        assert result.count("Total") == 1


class TestGenerateXLSX:
    def test_basic_xlsx(self):
        expenses = [
            {"date": "2025-06-15", "description": "lunch", "category": "Food", "amount": 350.0},
        ]
        result = generate_xlsx(expenses, 2025, 6)
        assert result.read(4) == b"PK\x03\x04"  # Valid xlsx (zip) header

    def test_empty_xlsx(self):
        result = generate_xlsx([], 2025, 6)
        assert result.read(4) == b"PK\x03\x04"


class TestGeneratePDF:
    def test_basic_pdf(self):
        expenses = [
            {"date": "2025-06-15", "description": "lunch", "category": "Food", "amount": 350.0},
        ]
        result = generate_pdf(expenses, 2025, 6)
        assert result.read(5) == b"%PDF-"

    def test_empty_pdf(self):
        result = generate_pdf([], 2025, 6)
        assert result.read(5) == b"%PDF-"

    def test_long_description_truncated(self):
        expenses = [
            {"date": "2025-06-15", "description": "a" * 100, "category": "Food", "amount": 100.0},
        ]
        result = generate_pdf(expenses, 2025, 6)
        assert result.read(5) == b"%PDF-"
