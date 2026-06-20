from groq import Groq
import os


def _get_client():
    key = os.environ.get("GROQ_API_KEY", "")
    return Groq(api_key=key) if key else None


def _has_api_key():
    return bool(os.environ.get("GROQ_API_KEY", ""))
