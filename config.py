import os
from zoneinfo import ZoneInfo

# ── Load .env file (supports multiline PEM values) ──
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as f:
        raw = f.readlines()
    entries = []
    buf = ""
    for line in raw:
        s = line.rstrip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            maybe_key = s.split("=", 1)[0].strip()
            if maybe_key.isidentifier():
                if buf:
                    entries.append(buf)
                buf = s
                continue
        if buf:
            buf += "\n" + s
    if buf:
        entries.append(buf)
    for entry in entries:
        key, _, val = entry.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        os.environ.setdefault(key, val)

SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-key")
TIMEZONE = ZoneInfo("Asia/Dhaka")

USERNAME = os.environ.get("APP_USERNAME", "admin")
PASSWORD = os.environ.get("APP_PASSWORD", "admin123")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@expenses.app")
VAPID_APPLICATION_SERVER_KEY = os.environ.get("VAPID_APPLICATION_SERVER_KEY", "")

DATABASE_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.db"),
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── Neon/Postgres connection enrichment ──
def enrich_db_url(url=None):
    """Auto-append connection params for Neon Postgres (cold-start mitigation)."""
    if url is None:
        url = DATABASE_URL
    if not url or not url.startswith("postgresql"):
        return url
    base, frag = (url.split("?", 1) + [""])[:2]
    params = dict(p.split("=", 1) for p in frag.split("&") if p)
    params.setdefault("connect_timeout", "10")
    params.setdefault("sslmode", "require")
    return base + "?" + "&".join(f"{k}={v}" for k, v in params.items())

SEED_CATEGORIES = {
    "chira": "Groceries",
    "muri": "Groceries",
    "shosha": "Groceries",
    "gajor": "Groceries",
    "aloo": "Groceries",
    "begun": "Groceries",
    "fulkopi": "Groceries",
    "badhakopi": "Groceries",
    "dherosh": "Groceries",
    "mula": "Groceries",
    "kumra": "Groceries",
    "lau": "Groceries",
    "korola": "Groceries",
    "potol": "Groceries",
    "shim": "Groceries",
    "kochu": "Groceries",
    "shak": "Groceries",
    "borboti": "Groceries",
    "murgi": "Groceries",
    "goru": "Groceries",
    "khashi": "Groceries",
    "hash": "Groceries",
    "dim": "Groceries",
    "rui": "Groceries",
    "chingri": "Groceries",
    "katla": "Groceries",
    "tilapia": "Groceries",
    "dudh": "Groceries",
    "dal": "Groceries",
    "chal": "Groceries",
    "tel": "Groceries",
    "badam": "Groceries",
    "peyaj": "Groceries",
    "ada": "Groceries",
    "holud": "Groceries",
    "dhonia": "Groceries",
    "jira": "Groceries",
    "shorshe": "Groceries",
    "aam": "Fruits",
    "kola": "Fruits",
    "apple": "Fruits",
    "komola": "Fruits",
    "peyara": "Fruits",
    "angur": "Fruits",
    "lichu": "Fruits",
    "tarmuj": "Fruits",
    "rickhaw": "Transport",
    "rickshaw": "Transport",
    "bus": "Transport",
    "cng": "Transport",
    "tempo": "Transport",
    "petrol": "Transport",
    "fuel": "Transport",
    "kacchi": "Dining Out",
    "khacci": "Dining Out",
    "biryani": "Dining Out",
    "biriani": "Dining Out",
    "pizza": "Dining Out",
    "burger": "Dining Out",
    "fuchka": "Dining Out",
    "chaat": "Dining Out",
    "mishti": "Dining Out",
    "misti": "Dining Out",
    "roshmalai": "Dining Out",
    "jilapi": "Dining Out",
    "oshudh": "Health",
    "electricity": "Bills",
    "bari bhara": "Rent",
    "jama": "Shopping",
    "movie": "Entertainment",
}

CATEGORY_COLORS = {
    "Food": "#10b981",
    "Dining Out": "#f43f5e",
    "Transport": "#3b82f6",
    "Shopping": "#ec4899",
    "Bills": "#f59e0b",
    "Entertainment": "#8b5cf6",
    "Health": "#ef4444",
    "Education": "#06b6d4",
    "Rent": "#6366f1",
    "Fruits": "#fb923c",
    "Groceries": "#84cc16",
    "Travel": "#f97316",
    "Personal Care": "#d946ef",
    "Gifts": "#e11d48",
    "Investment": "#14b8a6",
    "Savings": "#22c55e",
    "Other": "#6b7280",
}
