import pytest
from llm.decompose import is_question, _is_compound_question, _extract_text


class TestIsQuestion:
    def test_starts_with_question_word(self):
        assert is_question("how much did I spend") is True

    def test_starts_with_what(self):
        assert is_question("what is my total") is True

    def test_starts_with_show(self):
        assert is_question("show me expenses") is True

    def test_ends_with_question_mark(self):
        assert is_question("you spent 500?") is True

    def test_not_a_question(self):
        assert is_question("my total spending") is False

    def test_statement_with_period(self):
        assert is_question("i spent 500.") is False

    def test_single_question_word(self):
        assert is_question("why") is True

    def test_question_word_with_punctuation(self):
        assert is_question("how?") is True

    def test_empty_string(self):
        assert is_question("") is False


class TestIsCompoundQuestion:
    def test_and_what_indicator(self):
        assert _is_compound_question("how much on food and what about transport") is True

    def test_then_indicator(self):
        assert _is_compound_question("show food then transport") is True

    def test_also_indicator(self):
        assert _is_compound_question("show food also transport") is True

    def test_after_that_indicator(self):
        assert _is_compound_question("show food after that transport") is True

    def test_simple_question(self):
        assert _is_compound_question("how much on food") is False

    def test_empty_string(self):
        assert _is_compound_question("") is False

    def test_and_show_indicator(self):
        assert _is_compound_question("total food and show transport") is True


class TestExtractText:
    def test_dict_with_text_key(self):
        assert _extract_text({"text": "hello"}) == "hello"

    def test_dict_without_text_key(self):
        assert _extract_text({"answer": "hello"}) == "{'answer': 'hello'}"

    def test_plain_string(self):
        assert _extract_text("hello") == "hello"

    def test_empty_string(self):
        assert _extract_text("") == ""

    def test_empty_dict(self):
        assert _extract_text({}) == "{}"

    def test_none(self):
        assert _extract_text(None) == "None"
