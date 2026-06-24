from groq import Groq
import os
import sys

# ── Model selection ──
# Complex model for SQL generation, verification, decomposition, forecasting.
# Fast model for expense extraction and splitting.
COMPLEX_MODEL = os.environ.get("LLM_COMPLEX_MODEL", "llama-3.3-70b-versatile")
FAST_MODEL = os.environ.get("LLM_FAST_MODEL", "llama-3.1-8b-instant")

# Request timeout in seconds
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "15.0"))


def _get_client():
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        print(f"[WARN] GROQ_API_KEY not configured in environment variables", file=sys.stderr)
        print(f"[WARN] Expense extraction, Q&A, and forecasting will fall back to keyword matching or disabled", file=sys.stderr)
        return None
    try:
        return Groq(api_key=key, timeout=LLM_TIMEOUT)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Groq client: {e}", file=sys.stderr)
        return None


def _has_api_key():
    return bool(os.environ.get("GROQ_API_KEY", ""))
