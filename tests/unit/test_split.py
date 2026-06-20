import pytest
from llm.split import _clean_split_desc


class TestCleanSplitDesc:
    def test_removes_trailing_amount_with_taka(self):
        assert _clean_split_desc("gorur mangsho 500 taka") == "gorur mangsho"

    def test_removes_trailing_amount_with_tk(self):
        assert _clean_split_desc("mach 300 tk") == "mach"

    def test_removes_trailing_number_only(self):
        assert _clean_split_desc("rickshaw 50") == "rickshaw"

    def test_preserves_description_without_trailing_amount(self):
        assert _clean_split_desc("gorur mangsho") == "gorur mangsho"

    def test_preserves_quantity_modifier(self):
        result = _clean_split_desc("1 kg gorur mangsho")
        assert "1 kg" in result or result == "1 kg gorur mangsho"

    def test_handles_bengali_taka(self):
        assert _clean_split_desc("মুরগি ৫০০ টাকা") == "মুরগি"

    def test_handles_decimal_amount(self):
        assert _clean_split_desc("khabar 45.50 tk") == "khabar"

    def test_handles_multiple_spaces(self):
        assert _clean_split_desc("gorur  mangsho  500") == "gorur  mangsho"

    def test_empty_string(self):
        assert _clean_split_desc("") == ""

    def test_whitespace_stripped(self):
        assert _clean_split_desc("  rickshaw 50  ") == "rickshaw"

    def test_preserves_meaningful_numbers_in_middle(self):
        assert _clean_split_desc("2 kg chal 100") == "2 kg chal"
