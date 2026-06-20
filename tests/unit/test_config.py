import pytest
from config import _normalize_pem, enrich_db_url


class TestNormalizePem:
    def test_none_input(self):
        assert _normalize_pem(None) is None

    def test_empty_input(self):
        assert _normalize_pem("") == ""

    def test_no_begin_marker(self):
        assert _normalize_pem("just a string") == "just a string"

    def test_normalizes_pem(self):
        raw = "-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg\n-----END PRIVATE KEY-----"
        result = _normalize_pem(raw)
        assert result.startswith("-----BEGIN PRIVATE KEY-----")
        assert result.endswith("-----END PRIVATE KEY-----")
        assert "\n" in result

    def test_multiline_body_without_newlines(self):
        raw = "-----BEGIN PRIVATE KEY-----\n" + "a" * 128 + "\n" + "b" * 32 + "\n-----END PRIVATE KEY-----"
        result = _normalize_pem(raw)
        assert "-----BEGIN PRIVATE KEY-----\n" in result

    def test_no_match_returns_normalized(self):
        raw = "-----BEGIN SOMETHING----- stuff -----END SOMETHING-----"
        result = _normalize_pem(raw)
        assert "-----BEGIN PRIVATE KEY-----" in result


class TestEnrichDbUrl:
    def test_none_url(self):
        result = enrich_db_url(None)
        assert result is None or (isinstance(result, str) and result == "")

    def test_empty_url(self):
        assert enrich_db_url("") == ""

    def test_sqlite_url_unchanged(self):
        url = "sqlite:///expenses.db"
        assert enrich_db_url(url) == url

    def test_postgres_url_without_params(self):
        url = "postgresql://user:pass@host:5432/db"
        result = enrich_db_url(url)
        assert "connect_timeout=10" in result
        assert "sslmode=require" in result

    def test_postgres_url_with_existing_params(self):
        url = "postgresql://user:pass@host:5432/db?sslmode=prefer"
        result = enrich_db_url(url)
        assert "connect_timeout=10" in result
        assert "sslmode=require" not in result

    def test_postgres_url_with_all_params(self):
        url = "postgresql://user:pass@host:5432/db?connect_timeout=30&sslmode=prefer"
        result = enrich_db_url(url)
        assert "connect_timeout=30" in result
        assert "sslmode=prefer" in result

    def test_neon_postgres(self):
        url = "postgresql://user:pass@ep-example-123.us-east-2.aws.neon.tech/db"
        result = enrich_db_url(url)
        assert result.startswith("postgresql://")
        assert "connect_timeout=10" in result
