import re
import calendar
from datetime import date, timedelta, datetime
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
    _MONTH_RE = re.compile(
        r'\b(?:january|february|march|april|may|june|july|'
        r'august|september|october|november|december)\b',
        re.IGNORECASE,
    )

    def __init__(self):
        self._d = _fmt_dates()

    def match(self, question):
        q = question.strip()
        q_lower = q.lower()

        time_info = self._detect_time(q_lower)
        category = self._detect_category(q_lower)

        if not time_info["clause"] and self._MONTH_RE.search(q_lower) and not re.search(r'\b(?:between|from\s+\w+\s+to)\b', q_lower):
            if not category:
                return None

        for method in [
            self._match_budget,
            self._match_budgets_all,
            self._match_pacing,
            self._match_forecast,
            self._match_week_comparison,
            self._match_year_comparison,
            self._match_comparison,
            self._match_specific_date_range,
            self._match_combined_categories,
            self._match_most_expensive,
            self._match_top_n,
            self._match_most_recent,
            self._match_most_used_category,
            self._match_count_by_category,
            self._match_category_breakdown,
            self._match_daily_breakdown,
            self._match_average_daily,
            self._match_how_many,
            self._match_how_much_with_category,
            self._match_description_spend,
            self._match_date_highest_spend,
            self._match_amount_threshold,
            self._match_amount_range,
            self._match_how_much_total,
            self._match_year_to_date,
            self._match_show_expenses_by_category,
            self._match_show_expenses,
            self._match_unused_categories,
            self._match_category_comparison,
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
            r'\b(?:bought|buy|purchase|purchased|get|got)\s+(?:a\s+|an\s+|the\s+|some\s+)?(\w+(?:\s+\w+)?)',
            r'\b(?:spent|spend)\s+on\s+(?:a\s+|an\s+|the\s+)?(\w+(?:\s+\w+)?)',
            r'\bhow\s+much\s+(?:on|for)\s+(?:a\s+|an\s+|the\s+)?(\w+(?:\s+\w+)?)',
            r'(\w+(?:\s+\w+)?)\s+expenses',
        ]:
            m = re.search(pattern, q_lower)
            if m:
                phrase = m.group(1).strip().lower()
                parts = phrase.split()
                if parts and parts[0] not in _SKIP_WORDS and parts[0] not in self._CAT_SET:
                    valid = [parts[0]]
                    for p in parts[1:]:
                        if p in _SKIP_WORDS or p in self._CAT_SET:
                            break
                        valid.append(p)
                    return ' '.join(valid)
        return None

    def _description_where_clause(self, keyword, where_prefix):
        words = keyword.lower().split()
        clauses = []
        for w in words:
            safe = re.sub(r'[^\w\s]', '', w).replace('%', '').replace('_', '')[:50]
            clauses.append(f"LOWER(description) LIKE '%{safe}%'")
        if not clauses:
            return where_prefix
        joined = " AND ".join(clauses)
        if where_prefix:
            return where_prefix + " AND " + joined
        return joined

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
        if re.search(r'\b(?:compare|breakdown|vs|versus|budget|track|pacing|than)\b', q_lower):
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
            f"ROUND(CAST(COALESCE(SUM(amount), 0) / {days_elapsed} AS numeric), 0) as daily_avg, "
            f"{days_elapsed} as days_elapsed, {d['days_in_month']} as days_in_month "
            f"FROM expenses WHERE user_id = :uid AND date LIKE '{d['current_month']}%'"
        )
        return (sql, "pacing")

    def _match_forecast(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:projected?|forecast|will\s+i\s+spend|by\s+the\s+end\s+of\s+(?:the\s+)?month|end\s+of\s+month|gonna\s+spend|expect\s+to\s+spend)\b', q_lower):
            return None
        d = self._d
        days_elapsed = max(d['days_elapsed'], 1)
        sql = (
            f"SELECT COALESCE(SUM(amount), 0) as total, "
            f"ROUND(CAST(COALESCE(SUM(amount), 0) / {days_elapsed} AS numeric), 0) as daily_avg, "
            f"{days_elapsed} as days_elapsed, {d['days_in_month']} as days_in_month, "
            f"(SELECT COALESCE(amount, 0) FROM budgets WHERE user_id = :uid AND category = '__overall__') as budget_amount "
            f"FROM expenses WHERE user_id = :uid AND date LIKE '{d['current_month']}%'"
        )
        return (sql, "forecast")

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

    def _match_budgets_all(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:all\s+budget|show\s+.*budget|budget\s+status|budgets)\b', q_lower):
            return None
        if category:
            return None
        d = self._d
        sql = (
            f"SELECT b.category, b.amount as budget_amount, "
            f"COALESCE(e.spent, 0) as spent, "
            f"b.amount - COALESCE(e.spent, 0) as remaining "
            f"FROM budgets b "
            f"LEFT JOIN (SELECT category, SUM(amount) as spent FROM expenses "
            f"WHERE user_id = :uid AND date LIKE '{d['current_month']}%' GROUP BY category) e "
            f"ON e.category = b.category "
            f"WHERE b.user_id = :uid ORDER BY b.category"
        )
        return (sql, "budgets_all")

    def _match_week_comparison(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:this\s+week\s+vs|this\s+week\s+compare|week\s+over\s+week)\b', q_lower):
            if not (re.search(r'\bcompare\b', q_lower) and re.search(r'\blasts?\s+week\b', q_lower)):
                return None
        d = self._d
        sql = (
            f"SELECT 'This week' as period, COALESCE(SUM(amount), 0) as total "
            f"FROM expenses WHERE user_id = :uid "
            f"AND date >= '{d['week_start']}' AND date <= '{d['today']}' "
            f"UNION ALL "
            f"SELECT 'Last week', COALESCE(SUM(amount), 0) "
            f"FROM expenses WHERE user_id = :uid "
            f"AND date >= '{d['last_week_start']}' AND date < '{d['week_start']}'"
        )
        return (sql, "week_comparison")

    def _match_year_comparison(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:this\s+year\s+vs|this\s+year\s+compare|year\s+over\s+year)\b', q_lower):
            if not (re.search(r'\bcompare\b', q_lower) and re.search(r'\blast\s+year\b', q_lower)):
                return None
        d = self._d
        last_year = str(int(d['current_year']) - 1)
        sql = (
            f"SELECT SUBSTR(date, 1, 4) as year, COALESCE(SUM(amount), 0) as total "
            f"FROM expenses WHERE user_id = :uid "
            f"AND (date LIKE '{d['current_year']}%' OR date LIKE '{last_year}%') "
            f"GROUP BY SUBSTR(date, 1, 4) ORDER BY year"
        )
        return (sql, "year_comparison")

    def _match_specific_date_range(self, q, q_lower, time_info, category):
        m = re.search(r'\bbetween\s+(\w+\s+\d+)\s+and\s+(\w+\s+\d+)\b', q_lower)
        if not m:
            m = re.search(r'\bfrom\s+(\w+\s+\d+)\s+to\s+(\w+\s+\d+)\b', q_lower)
        if not m:
            m = re.search(r'\bfrom\s+(\w+\s+\d+)\s+(?:through|until|till)\s+(\w+\s+\d+)\b', q_lower)
        if not m:
            return None
        this_year = self._d['current_year']
        last_year = str(int(this_year) - 1)
        try:
            start = datetime.strptime(m.group(1).title() + f" {this_year}", "%B %d %Y")
            end = datetime.strptime(m.group(2).title() + f" {this_year}", "%B %d %Y")
        except ValueError:
            return None
        if end < start:
            start = datetime.strptime(m.group(1).title() + f" {last_year}", "%B %d %Y")
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        where = self._where_clause(time_info, category)
        if "user_id = :uid" in where:
            where += f" AND date >= '{start_str}' AND date <= '{end_str}'"
        else:
            where = f"user_id = :uid AND date >= '{start_str}' AND date <= '{end_str}'"
        if self._has_aggregate_intent(q_lower):
            sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        else:
            sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY date LIMIT 50"
        return (sql, "date_range")

    def _match_combined_categories(self, q, q_lower, time_info, category):
        m = re.search(r'\bhow\s+much\s+on\s+(.+?)\s+(?:and|&)\s+(.+?)\s+(?:combined|totals?|spending|expenses?|this|last|total)?\s*(?:month|week|year)?\s*$', q_lower.strip().rstrip('?.!,'))
        if not m:
            return None
        raw1 = m.group(1).strip()
        raw2 = m.group(2).strip()
        cat1 = raw1[0].upper() + raw1[1:] if raw1 else raw1
        cat2 = raw2[0].upper() + raw2[1:] if raw2 else raw2
        cats = []
        for c in _ALL_CATEGORIES:
            if c.lower() in cat1.lower() or cat1.lower() in c.lower():
                cats.append(c)
            elif c.lower() in cat2.lower() or cat2.lower() in c.lower():
                cats.append(c)
        if len(cats) < 2:
            return None
        cats_str = ", ".join(f"'{c}'" for c in cats)
        where = self._where_clause(time_info)
        if "user_id = :uid" in where:
            where += f" AND category IN ({cats_str})"
        else:
            where = f"user_id = :uid AND category IN ({cats_str})"
        sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "combined_categories")

    def _match_amount_threshold(self, q, q_lower, time_info, category):
        m = re.search(r'\b(over|above|more\s+than|greater\s+than|exceeding)\s+(\d+)\b', q_lower)
        direction = ">"
        if not m:
            m = re.search(r'\b(under|below|less\s+than|lower\s+than|at\s+most)\s+(\d+)\b', q_lower)
            direction = "<"
        if not m:
            return None
        amount = int(m.group(2))
        where = self._where_clause(time_info, category)
        if "user_id = :uid" in where:
            where += f" AND amount {direction} {amount}"
        else:
            where = f"user_id = :uid AND amount {direction} {amount}"
        if self._has_list_intent(q_lower) or not self._has_aggregate_intent(q_lower):
            sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY amount DESC LIMIT 50"
        else:
            sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "amount_threshold")

    def _match_daily_breakdown(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:each\s+day|per\s+day|daily\s+breakdown|day\s+by\s+day|spend\s+each\s+day|day\'s\s+spending)\b', q_lower):
            return None
        if not time_info or not time_info["clause"]:
            return None
        where = "user_id = :uid AND " + time_info["clause"]
        sql = f"SELECT date, COALESCE(SUM(amount), 0) as total FROM expenses WHERE {where} GROUP BY date ORDER BY date"
        return (sql, "daily_breakdown")

    def _match_most_used_category(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:most\s+used|most\s+frequent|which\s+category.*most|use\s+the\s+most)\b', q_lower):
            return None
        if category:
            return None
        if not time_info or not time_info["clause"]:
            return None
        where = "user_id = :uid AND " + time_info["clause"]
        sql = f"SELECT category, COUNT(*) as count FROM expenses WHERE {where} GROUP BY category ORDER BY count DESC LIMIT 1"
        return (sql, "most_used_category")

    def _match_year_to_date(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:year\s+to\s+date|ytd|this\s+year\s+so\s+far|total.*this\s+year|spent.*this\s+year)\b', q_lower):
            return None
        d = self._d
        where = self._where_clause(None, category)
        if "user_id = :uid" in where:
            where += f" AND date LIKE '{d['current_year']}%'"
        else:
            where = f"user_id = :uid AND date LIKE '{d['current_year']}%'"
        sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "year_to_date")

    def _match_most_recent(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:last\s+expense|most\s+recent\s+expense|latest\s+expense|last\s+transaction|most\s+recent\s+transaction)\b', q_lower):
            return None
        if self._has_aggregate_intent(q_lower):
            return None
        where = self._where_clause(time_info, category)
        sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY date DESC, id DESC LIMIT 1"
        return (sql, "most_recent")

    def _match_description_spend(self, q, q_lower, time_info, category):
        if not self._has_aggregate_intent(q_lower):
            return None
        if category:
            return None
        keyword = self._detect_item_keyword(q_lower)
        if not keyword or keyword in [c.lower() for c in _ALL_CATEGORIES]:
            return None
        where = self._where_clause(time_info)
        where = self._description_where_clause(keyword, where)
        sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "description_spend")

    def _match_count_by_category(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:count.*category|frequency.*category|how\s+many.*per)\b', q_lower):
            if not (re.search(r'\bcount\b', q_lower) and re.search(r'\bcategor', q_lower)):
                return None
        if not time_info or not time_info["clause"]:
            return None
        where = "user_id = :uid AND " + time_info["clause"]
        if category:
            where += f" AND category = '{category}'"
            sql = f"SELECT COUNT(*) as count FROM expenses WHERE {where}"
        else:
            sql = f"SELECT category, COUNT(*) as count FROM expenses WHERE {where} GROUP BY category ORDER BY count DESC"
        return (sql, "count_by_category")

    def _match_amount_range(self, q, q_lower, time_info, category):
        m = re.search(r'\b(?:between|from)\s+(\d+)\s+(?:and|to)\s+(\d+)\b', q_lower)
        if not m:
            return None
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        where = self._where_clause(time_info, category)
        if "user_id = :uid" in where:
            where += f" AND amount BETWEEN {lo} AND {hi}"
        else:
            where = f"user_id = :uid AND amount BETWEEN {lo} AND {hi}"
        if self._has_list_intent(q_lower) or not self._has_aggregate_intent(q_lower):
            sql = f"SELECT date, description, amount, category FROM expenses WHERE {where} ORDER BY amount DESC LIMIT 50"
        else:
            sql = f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE {where}"
        return (sql, "amount_range")

    def _match_unused_categories(self, q, q_lower, time_info, category):
        if not re.search(r'\b(?:not\s+(?:spend|used|spent)|never\s+(?:used|spent)|didn\'?t\s+(?:spend|use)|haven\'?t\s+(?:spent|used)|no\s+(?:spending|expenses?)|without|excluding|unused|did\s+not\s+(?:spend|use))\b', q_lower):
            return None
        if not time_info or not time_info["clause"]:
            return None
        tc = time_info["clause"]
        cat_union = " UNION ALL ".join(f"SELECT '{c}' as cat_name" for c in _ALL_CATEGORIES)
        sql = (
            f"WITH all_cats AS ({cat_union}), "
            f"used AS (SELECT DISTINCT category FROM expenses "
            f"WHERE user_id = :uid AND {tc}) "
            f"SELECT cat_name as category FROM all_cats "
            f"WHERE cat_name NOT IN (SELECT category FROM used)"
        )
        return (sql, "unused_categories")

    def _match_category_comparison(self, q, q_lower, time_info, category):
        m = re.search(r'\bhow\s+much\s+more\s+(?:on|for)\s+(.+?)\s+(?:than|vs\.?|versus)\s+(.+?)\s*(?:\?|$)', q_lower)
        if not m:
            m = re.search(r'\b(?:more|less)\s+on\s+(.+?)\s+(?:than|vs\.?|versus)\s+(.+?)\s*(?:\?|$)', q_lower)
        if not m:
            return None
        raw1 = m.group(1).strip()
        raw2 = m.group(2).strip()
        def _match_cat(raw):
            rl = raw.lower()
            for c in sorted(_ALL_CATEGORIES, key=len, reverse=True):
                if c.lower() in rl:
                    return c
            return None
        cat1 = _match_cat(raw1)
        cat2 = _match_cat(raw2)
        if not cat1 or not cat2:
            return None
        where = self._where_clause(time_info, None)
        sql = (
            f"SELECT '{cat1}' as category, COALESCE(SUM(CASE WHEN category = '{cat1}' THEN amount END), 0) as total "
            f"FROM expenses WHERE {where} "
            f"UNION ALL "
            f"SELECT '{cat2}', COALESCE(SUM(CASE WHEN category = '{cat2}' THEN amount END), 0) "
            f"FROM expenses WHERE {where}"
        )
        return (sql, "category_comparison")
