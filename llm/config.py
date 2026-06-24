from groq import Groq
import os

# ── Model selection ──
# Complex model for SQL generation, verification, decomposition, forecasting.
# Fast model for expense extraction and splitting.
COMPLEX_MODEL = os.environ.get("LLM_COMPLEX_MODEL", "llama-3.3-70b-versatile")
FAST_MODEL = os.environ.get("LLM_FAST_MODEL", "llama-3.1-8b-instant")


def _get_client():
    key = os.environ.get("GROQ_API_KEY", "")
    return Groq(api_key=key) if key else None


def _has_api_key():
    return bool(os.environ.get("GROQ_API_KEY", ""))
