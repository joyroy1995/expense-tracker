from groq import Groq
import httpx
import os
import re
import sys

_DOTENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def _read_env(key):
    val = os.environ.get(key)
    if val:
        return val
    try:
        with open(_DOTENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""

# ── Model selection ──
# Complex model for SQL generation, verification, decomposition, forecasting.
# Fast model for expense extraction and splitting.
COMPLEX_MODEL = os.environ.get("LLM_COMPLEX_MODEL", "llama-3.3-70b-versatile")
FAST_MODEL = os.environ.get("LLM_FAST_MODEL", "llama-3.1-8b-instant")

# Request timeout in seconds
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "15.0"))


def _get_client():
    key = _read_env("GROQ_API_KEY")
    if not key:
        print(f"[WARN] GROQ_API_KEY not configured in environment variables or .env", file=sys.stderr)
        print(f"[WARN] Expense extraction, Q&A, and forecasting will fall back to keyword matching or disabled", file=sys.stderr)
        return None
    http_client = httpx.Client(verify=False, timeout=LLM_TIMEOUT)
    try:
        return Groq(api_key=key, timeout=LLM_TIMEOUT, http_client=http_client, max_retries=0)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Groq client: {e}", file=sys.stderr)
        return None


def _has_api_key():
    return bool(_read_env("GROQ_API_KEY"))
