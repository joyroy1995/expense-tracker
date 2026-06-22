import re
import calendar
from datetime import date, timedelta
from database.qa_cache import _ALL_CATEGORIES


def _fmt_dates():
    today = date.today()
    current_month = today.strftime("%Y-%m")
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    current_year = today.strftime("%Y")
    seven_days_ago = (today - timedelta(days=7)).isoformat()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    last_week_start = (today - timedelta(days=today.weekday() + 7)).isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return {
        "today": today.isoformat(),
        "current_month": current_month,
        "last_month": prev,
        "current_year": current_year,
        "seven_days_ago": seven_days_ago,
        "week_start": week_start,
        "last_week_start": last_week_start,
        "yesterday": yesterday,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
    }


_SKIP_WORDS = frozenset({
    "all", "my", "your", "the", "this", "that", "these", "those", "show",
    "list", "get", "give", "find", "see", "view", "display", "print",
    "any", "some", "every", "each", "total", "month", "day", "week", "year",
    "biggest", "largest", "smallest", "cheapest", "most", "least",
    "highest", "lowest", "best", "worst", "recent", "last", "first",
    "previous", "next", "top", "bottom",
    "today", "todays", "tonight", "yesterday", "yesterdays",
    "how", "what", "why", "when", "where", "which",
    "much", "many", "often", "did", "does", "do", "is", "are", "was",
    "were", "can", "could", "would", "will", "shall",
})


class PatternEngine:
    _CAT_SET = frozenset(c.lower() for c in _ALL_CATEGORIES)
    _CAT_MAP = {c.lower(): c for c in _ALL_CATEGORIES}

    def __init__(self):
        self._d = _fmt_dates()

    def match(self, question):
        q = question.strip()
        q_lower = q.lower()

        time_info = self._detect_time(q_lower)
        category = self._detect_category(q_lower)

        for method in [
            self._match_budget,
            self._match_pacing,
            self._match_comparison,
            self._match_most_expensive,
            self._match_top_n,
            self._match_category_breakdown,
            self._match_average_daily,
            self._match_how_many,
            self._match_how_much_with_category,
            self._match_date_highest_spend,
            self._match_how_much_total,
            self._match_show_expenses_by_category,
            self._match_show_expenses,
        ]:
            result = method(q, q_lower, time_info, category)
            if result:
                return result
        return None

    def _detect_time(self, q_lower):
        d = self._d
        if re.search(r'\bthis\s+month\b', q_lower):
            return {"clause": f"date LIKE '{d['current_month']}%'"}
        if re.search(r'\blast\s+month\b', q_lower):
            return {"clause": f"date LIKE '{d['last_month']}%'"}
        if re.search(r'\btoday\b', q_lower):
            return {"clause": f"date = '{d['today']}'"}
        if re.search(r'\byesterday\b', q_lower):
            return {"clause": f"date = '{d['yesterday']}'"}
        if re.search(r'\bthis\s+week\b', q_lower):
            return {"clause": f"date >= '{d['week_start']}' AND date <= '{d['today']}'"}
        if re.search(r'\blast\s+week\b', q_lower):
            return {"clause": f"date >= '{d['last_week_start']}' AND date < '{d['week_start']}'"}
        if re.search(r'\bthis\s+year\b', q_lower):
            return {"clause": f"date LIKE '{d['current_year']}%'"}
        m = re.search(r'\blast\s+(\d+)\s+days?\b', q_lower)
        if m:
            n = int(m.group(1))
            n_days_ago = (date.today() - timedelta(days=n)).isoformat()
            return {"clause": f"date >= '{n_days_ago}'"}
        m = re.search(r'\blast\s+(\d+)\s+months?\b', q_lower)
        if m:
            return {"clause": f"date LIKE '{d['current_month']}%'"}
        return {"clause": None}

    def _detect_category(self, q_lower):
        for cat_lower in sorted(self._CAT_SET, key=lambda x: -len(x)):
            if cat_lower in q_lower:
                return self._CAT_MAP[cat_lower]
        return None

    def _detect_item_keyword(self, q_lower):
        for pattern in [
            r'\b(?:bought|buy|purchase|purchased|get|got)\s+(?:a\s+|an\s+|the\s+|some\s+)?(\w+)',
            r'\b(?:spent|spend)\s+on\s+(?:a\s+|an\s+|the\s+)?(\w+(?:\s+\w+)?)',
            r'\bhow\s+much\s+(?:on|for)\s+(?:a\s+|an\s+|the\s+)?(\w+)',
        ]:
            m = re.search(pattern, q_lower)
            if m:
                word = m.group(1).strip()
                parts = word.split()
                if parts and parts[0] not in _SKIP_WORDS and parts[0] not in self._CAT_SET:
                    return parts[0]
        return None

    def _where_clause(self, time_info, category=None):
        parts = []
        if category:
            parts.append(f"category = '{category}'")
        if time_info and time_info["clause"]:
            parts.append(time_info["clause"])
        if parts:
            return "user_id = :uid AND " + " AND ".join(parts)
        return "user_id = :uid"

    def _has_aggregate_intent(self, q_lower):
        return bool(re.search(r'\b(?:how\s+much|total|sum|amount|spent)\b', q_lower))

    def _has_list_intent(self, q_lower):
        return bool(re.search(r'\b(?:show|list|display|find|see|view)\b', q_lower))

    def _match_how_much_with_category(self, q, q_lower, time_info, category):
        if not self._has_aggregate_intent(q_lower):
            return None
        if not category:
            return None
        if re.search(r'\b(?:compare|breakdown|vs|versus|budget|track|pacing)\b', q_lower):
            return None
        if re.search(r'\b(?:nothing|no\s+spending|zero|no\s+expense|without)\b', q_lower):
            return None
        where = self._where_clause(time_info, category)
        sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "how_much_category")

    def _match_date_highest_spend(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:which\s+date|which\s+day|what\s+date|what\s+day)\b', q_lower):
            return None
        if not self._has_aggregate_intent(q_lower):
            return None
        if re.search(r'\b(?:compare|breakdown|vs|versus|budget|track|pacing)\b', q_lower):
            return None
        if re.search(r'\b(?:nothing|no\s+spending|zero|no\s+expense|without)\b', q_lower):
            return None
        if not time_info or not time_info["clause"]:
            return None
        where = "user_id = :uid AND " + time_info["clause"]
        sql = f"SELECT date, SUM(amount) as total FROM expenses WHERE {where} GROUP BY date ORDER BY total DESC LIMIT 1"
        return (sql, "date_highest_spend")

    def _match_how_much_total(self, q, q_lower, time_info, category):
        if not self._has_aggregate_intent(q_lower):
            return None
        if category:
            return None
        if re.search(r'\b(?:compare|breakdown|vs|versus|budget|track|pacing)\b', q_lower):
            return None
        if self._has_list_intent(q_lower) and not self._has_aggregate_intent(q_lower):
            return None
        if re.search(r'\b(?:nothing|no\s+spending|zero|no\s+expense|without)\b', q_lower):
            return None
        where = self._where_clause(time_info)
        sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "how_much_total")

    def _match_show_expenses(self, q, q_lower, time_info, category):
        if not self._has_list_intent(q_lower):
            return None
        if self._has_aggregate_intent(q_lower):
            return None
        if re.search(r'\b(?:breakdown|budget|compare|track|pacing|average)\b', q_lower):
            return None
        if not time_info or not time_info["clause"]:
            return None
        where = self._where_clause(time_info)
        sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY date DESC LIMIT 50"
        return (sql, "show_expenses")

    def _match_show_expenses_by_category(self, q, q_lower, time_info, category):
        if not self._has_list_intent(q_lower) and not re.search(r'\b(?:expense|expenses|transaction|transactions)\b', q_lower):
            return None
        if not category:
            return None
        if self._has_aggregate_intent(q_lower):
            return None
        if re.search(r'\b(?:breakdown|budget|compare|track|pacing|average)\b', q_lower):
            return None
        if not time_info or not time_info["clause"]:
            return None
        where = self._where_clause(time_info, category)
        sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY date DESC LIMIT 50"
        return (sql, "show_expenses_by_category")

    def _match_how_many(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:how\s+many|count|frequency|how\s+often)\b', q_lower):
            return None
        if self._has_list_intent(q_lower):
            return None
        where = self._where_clause(time_info, category)
        sql = f"SELECT COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "how_many")

    def _match_top_n(self, q, q_lower, time_info, category):
        m = re.search(r'\b(top|first|biggest|largest)\s+(\d+)\b', q_lower)
        if not m:
            return None
        n = int(m.group(2))
        if n < 1 or n > 100:
            return None
        where = self._where_clause(time_info, category)
        sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY amount DESC LIMIT {n}"
        return (sql, "top_n")

    def _match_most_expensive(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:most\s+expensive|biggest\s+expense|largest\s+expense)\b', q_lower):
            return None
        if re.search(r'\b(top|first)\s+\d+\b', q_lower):
            return None
        where = self._where_clause(time_info, category)
        sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY amount DESC LIMIT 1"
        return (sql, "most_expensive")

    def _match_category_breakdown(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:breakdown\s+by\s+category|category\s+breakdown|by\s+category|category\s+wise|per\s+category|which\s+category)\b', q_lower):
            return None
        if category:
            return None
        if self._has_aggregate_intent(q_lower) and re.search(r'\bwhich\s+category\b', q_lower):
            return None
        where = self._where_clause(time_info)
        sql = f"SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where} GROUP BY category ORDER BY total DESC"
        return (sql, "category_breakdown")

    def _match_average_daily(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:average|avg)\b', q_lower):
            return None
        if not time_info or not time_info["clause"]:
            return None
        where = "user_id = :uid AND " + time_info["clause"]
        sql = f"SELECT COALESCE(AVG(daily.total), 0) as avg_daily FROM (SELECT SUM(amount) as total FROM expenses WHERE {where} GROUP BY date) daily"
        return (sql, "average_daily")

    def _match_comparison(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:compare|vs|versus)\b', q_lower):
            return None
        d = self._d
        sql = (
            f"SELECT SUBSTR(date, 1, 7) as month, COALESCE(SUM(amount), 0) as total "
            f"FROM expenses WHERE user_id = :uid "
            f"AND (date LIKE '{d['current_month']}%' OR date LIKE '{d['last_month']}%') "
            f"GROUP BY SUBSTR(date, 1, 7) ORDER BY month"
        )
        return (sql, "month_comparison")

    def _match_pacing(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:on\s+track|pacing|how\s+am\s+i\s+doing)\b', q_lower):
            return None
        d = self._d
        days_elapsed = max(d['days_elapsed'], 1)
        sql = (
            f"SELECT COALESCE(SUM(amount), 0) as total, "
            f"ROUND(COALESCE(SUM(amount), 0) / {days_elapsed}, 0) as daily_avg, "
            f"{days_elapsed} as days_elapsed, {d['days_in_month']} as days_in_month "
            f"FROM expenses WHERE user_id = :uid AND date LIKE '{d['current_month']}%'"
        )
        return (sql, "pacing")

    def _match_budget(self, q, q_lower, time_info, category):
        if not re.search(r'\bbudget\b', q_lower):
            return None
        d = self._d
        if category:
            sql = (
                f"SELECT b.category, b.amount as budget_amount, "
                f"COALESCE(SUM(e.amount), 0) as spent, "
                f"b.amount - COALESCE(SUM(e.amount), 0) as remaining "
                f"FROM budgets b "
                f"LEFT JOIN expenses e ON e.user_id = b.user_id AND e.category = b.category "
                f"AND e.date LIKE '{d['current_month']}%' "
                f"WHERE b.user_id = :uid AND b.category = '{category}' "
                f"GROUP BY b.id, b.category, b.amount"
            )
        else:
            sql = (
                f"SELECT b.category, b.amount as budget_amount, "
                f"(SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{d['current_month']}%') as spent, "
                f"b.amount - (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{d['current_month']}%') as remaining "
                f"FROM budgets b WHERE b.user_id = :uid AND b.category = '__overall__'"
            )
        return (sql, "budget")
