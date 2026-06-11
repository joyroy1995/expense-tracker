import os

SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-key")

USERNAME = os.environ.get("APP_USERNAME", "admin")
PASSWORD = os.environ.get("APP_PASSWORD", "admin123")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

DATABASE_PATH = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.db"),
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

CATEGORY_COLORS = {
    "Food": "#10b981",
    "Transport": "#3b82f6",
    "Shopping": "#ec4899",
    "Bills": "#f59e0b",
    "Entertainment": "#8b5cf6",
    "Health": "#ef4444",
    "Education": "#06b6d4",
    "Rent": "#6366f1",
    "Groceries": "#84cc16",
    "Travel": "#f97316",
    "Personal Care": "#d946ef",
    "Gifts": "#e11d48",
    "Investment": "#14b8a6",
    "Savings": "#22c55e",
    "Other": "#6b7280",
}
