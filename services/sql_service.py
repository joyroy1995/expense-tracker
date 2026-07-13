import re
from datetime import datetime, timedelta
from config import TIMEZONE
from database import _ALL_CATEGORIES
from services.sql_ast import add_condition, remove_condition, replace_condition, has_condition


_KNOWN_TABLES = {"expenses", "users", "budgets", "learned_categories", "password_resets"}
_KNOWN_COLUMNS = {
    "expenses": {"id", "date", "description", "amount", "category", "user_id", "created_at"},
    "users": {"id", "username", "password_hash", "role", "created_at"},
    "budgets": {"id", "user_id", "category", "amount", "created_at", "updated_at"},
}

_SKIP_WORDS = frozenset({
    'all', 'my', 'your', 'the', 'this', 'that', 'these', 'those', 'show',
    'list', 'get', 'give', 'find', 'see', 'view', 'display', 'print',
    'any', 'some', 'every', 'each', 'total', 'month', 'day', 'week', 'year',
    'date', 'biggest', 'largest', 'smallest', 'cheapest', 'most', 'least',
    'highest', 'lowest', 'best', 'worst', 'recent', 'last', 'first',
    'previous', 'next', 'top', 'bottom',
    'today', 'todays', 'tonight', 'yesterday', 'yesterdays',
    'how', 'what', 'why', 'when', 'where', 'which',
    'much', 'many', 'often', 'did', 'does', 'do', 'is', 'are', 'was',
    'were', 'can', 'could', 'would', 'will', 'shall',
    'expensive', 'costly', 'pricey', 'overall', 'me', 'of',
})

_SORT_COL_MAP = {
    'amount': 'amount', 'money': 'amount', 'spending': 'amount', 'cost': 'amount',
    'date': 'date', 'day': 'date', 'time': 'date',
    'category': 'category',
    'description': 'description', 'name': 'description', 'item': 'description',
}

_ORDINAL_MAP = {
    'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
    'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
}


class SqlService:

    @staticmethod
    def validate_sql(sql):
        s = sql.strip()
        while s.endswith(";"):
            s = s[:-1].strip()
        if ";" in s:
            return False
        if not s.upper().startswith("SELECT"):
            return False
        if "--" in s or "/*" in s or "*/" in s:
            return False
        forbidden = {"DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE", "REPLACE", "EXEC"}
        words = re.findall(r'\b\w+\b', s.upper())
        for word in words:
            if word in forbidden:
                return False
        if s.count("(") != s.count(")"):
            return False
        table_refs = re.findall(r'(?:FROM|JOIN)\s+(\w+)', s, re.IGNORECASE)
        for t in table_refs:
            if t.lower() not in _KNOWN_TABLES:
                return False
        return True

    @staticmethod
    def ensure_user_filter(sql):
        if ":uid" in sql:
            return sql
        clauses = ["ORDER BY", "GROUP BY", "LIMIT", "HAVING"]
        sql_upper = sql.upper()
        insert_pos = len(sql)
        for clause in clauses:
            pos = sql_upper.find(clause)
            if pos != -1 and pos < insert_pos:
                insert_pos = pos
        prefix = sql[:insert_pos].upper()
        if "WHERE" in prefix:
            return sql[:insert_pos] + " AND user_id = :uid " + sql[insert_pos:]
        return sql[:insert_pos] + " WHERE user_id = :uid " + sql[insert_pos:]

    @staticmethod
    def fix_category_in_sql(sql, question):
        question_lower = question.lower()
        mentioned = None
        for cat in sorted(_ALL_CATEGORIES, key=len, reverse=True):
            if cat.lower() in question_lower:
                mentioned = cat
                break
        if not mentioned:
            if has_condition(sql, "__overall__"):
                return sql
            sql = remove_condition(sql, "category =")
            return sql
        if has_condition(sql, "category ="):
            for cat in _ALL_CATEGORIES:
                if f"category = '{cat}'" in sql or f"b.category = '{cat}'" in sql:
                    sql_cat = cat
                    break
            else:
                return add_condition(sql, f"category = '{mentioned}'")
            if sql_cat == mentioned or sql_cat == "__overall__":
                return sql
            return replace_condition(sql, "category =", f"category = '{mentioned}'")
        return add_condition(sql, f"category = '{mentioned}'")

    @staticmethod
    def fix_sort_order(sql, question):
        if not re.search(r'\b(?:descending|desc|newest\s*first|reverse)\b', question, re.IGNORECASE):
            return sql
        sql_upper = sql.upper()
        idx = sql_upper.find('ORDER BY')
        if idx == -1:
            return sql
        rest = sql_upper[idx + 9:]
        if 'DESC' in rest:
            return sql
        insert_pos = len(sql)
        for kw in ['LIMIT', 'OFFSET', 'HAVING']:
            pos = rest.find(kw)
            if pos != -1 and (idx + 9 + pos) < insert_pos:
                insert_pos = idx + 9 + pos
        return sql[:insert_pos] + ' DESC ' + sql[insert_pos:].lstrip()

    @staticmethod
    def fix_sort_column(sql, question):
        m = re.search(r'(?:sort|order)\s+by\s+(\w+)', question, re.IGNORECASE)
        if not m:
            return sql
        col = m.group(1).lower()
        col = _SORT_COL_MAP.get(col)
        if not col:
            return sql
        if not re.search(r'ORDER\s+BY', sql, re.IGNORECASE):
            return sql
        sql = re.sub(
            r'ORDER\s+BY\s+\w+(\s+(?:ASC|DESC))?',
            f'ORDER BY {col} DESC',
            sql,
            flags=re.IGNORECASE,
        )
        return sql

    @staticmethod
    def fix_frequency_sql(sql, question):
        if not re.search(r'\b(?:frequency|how\s+many\s+times|how\s+often|most\s+frequent|most\s+used|use\s+the\s+most|used\s+the\s+most|count)\b', question, re.IGNORECASE):
            return sql
        sql_upper = sql.upper()
        if 'SUM' not in sql_upper and 'GROUP BY' not in sql_upper:
            return sql
        if 'COUNT(*)' in sql_upper or 'COUNT(1)' in sql_upper:
            return sql
        sql = re.sub(
            r'COALESCE\(\s*SUM\(\s*amount\s*\)\s*,\s*0\s*\)\s+as\s+total',
            'COUNT(*) as count',
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r'SUM\(\s*amount\s*\)\s+as\s+total',
            'COUNT(*) as count',
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(r'ORDER\s+BY\s+total\s+DESC', 'ORDER BY count DESC', sql, flags=re.IGNORECASE)
        return sql

    @staticmethod
    def fix_top_n_limit(sql, question):
        m = re.search(r'\b(top|last|first)\s+(\d+)\b', question, re.IGNORECASE)
        if not m:
            return sql
        rest = question[m.end():].strip()
        if re.match(r'\b(day|days|week|weeks|month|months|year|years|hour|hours)\b', rest, re.IGNORECASE):
            return sql
        n = int(m.group(2))
        if 'LIMIT' in sql.upper():
            sql = re.sub(r'LIMIT\s+\d+', f'LIMIT {n}', sql, flags=re.IGNORECASE)
        return sql

    @staticmethod
    def fix_limit_syntax(sql, question):
        m = re.search(r'LIMIT\s+(\d+)\s*,\s*(\d+)', sql, re.IGNORECASE)
        if not m:
            return sql
        offset = m.group(1)
        limit = m.group(2)
        return sql[:m.start()] + f'LIMIT {limit} OFFSET {offset}' + sql[m.end():]

    @staticmethod
    def fix_ordinal_limit(sql, question):
        if re.search(
            r'\b\d+(?:st|nd|rd|th)\s+(?:january|february|march|april|may|june|july|'
            r'august|september|october|november|december)\b',
            question, re.IGNORECASE,
        ) or re.search(
            r'\b(?:january|february|march|april|may|june|july|'
            r'august|september|october|november|december)\s+\d+(?:st|nd|rd|th)\b',
            question, re.IGNORECASE,
        ):
            return sql
        m = re.search(r'\b(second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th))\b', question, re.IGNORECASE)
        if not m:
            return sql
        if re.search(r'\b(?:SUM|COUNT|AVG|COALESCE)\s*\(', sql, re.IGNORECASE):
            return sql
        word = m.group(1).lower()
        if word in _ORDINAL_MAP:
            n = _ORDINAL_MAP[word]
        else:
            n = int(re.sub(r'[^\d]', '', word))
        offset_val = n - 1
        singular = bool(re.search(r'\b(item|expense|transaction|purchase)\b', question, re.IGNORECASE) and
                        not re.search(r'\b(items|expenses|transactions|purchases)\b', question, re.IGNORECASE))
        if 'OFFSET' in sql.upper():
            if singular:
                sql = re.sub(r'LIMIT\s+\d+', 'LIMIT 1', sql, flags=re.IGNORECASE)
            sql = re.sub(r'OFFSET\s+\d+', f'OFFSET {offset_val}', sql, flags=re.IGNORECASE)
        else:
            if 'LIMIT' in sql.upper():
                if singular:
                    sql = re.sub(r'LIMIT\s+\d+', f'LIMIT 1 OFFSET {offset_val}', sql, flags=re.IGNORECASE)
                else:
                    sql = re.sub(r'LIMIT\s+\d+', f'LIMIT 50 OFFSET {offset_val}', sql, flags=re.IGNORECASE)
            else:
                limit_val = 1 if singular else 50
                sql += f' LIMIT {limit_val} OFFSET {offset_val}'
        return sql

    @staticmethod
    def fix_most_expensive_sql(sql, question):
        q = question.lower()
        if not re.search(r'\b(?:most\s+expensive|biggest\s+expense|largest\s+expense)\b', q):
            return sql
        if re.search(r'\bORDER\s+BY\b', sql, re.IGNORECASE):
            return sql
        if re.search(r'\b(?:SUM|COUNT|AVG|COALESCE)\s*\(', sql, re.IGNORECASE):
            return sql
        if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
            return sql
        sql = sql.rstrip().rstrip(';').strip()
        sql += ' ORDER BY amount DESC LIMIT 1'
        return sql

    @staticmethod
    def fix_category_breakdown_sql(sql, question):
        q = question.lower()
        if not re.search(r'\b(?:breakdown\s+by\s+category|category\s+breakdown|by\s+category|which\s+category|spend\s+the\s+most\s+on|spent\s+the\s+most\s+on|category\s+wise|per\s+category|group\s+by\s+category|top\s+\d+\s+categor(?:y|ies)\s+by|categories?\s+by\s+spending)\b', q):
            return sql
        if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
            return sql
        parts = re.split(r'\bFROM\b', sql, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) < 2:
            return sql
        from_clause = parts[1].strip()
        for kw in [' ORDER BY ', ' LIMIT ', ' OFFSET ', ' HAVING ']:
            pos = from_clause.upper().find(kw)
            if pos != -1:
                from_clause = from_clause[:pos]
        return f"SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM {from_clause} GROUP BY category ORDER BY total DESC"

    @staticmethod
    def fix_history_id_filter(sql, question):
        exclusion_kw = re.search(
            r'\b(?:other\s+than|except|excluding|exclude|not\s+including|without|but\s+not|aside\s+from)\b',
            question, re.IGNORECASE,
        )
        if exclusion_kw:
            return sql
        sql = re.sub(
            r'\s+AND\s+(?:expenses\.|e\.)?id\s*!=\s*\d+',
            '',
            sql,
            flags=re.IGNORECASE,
        )
        return sql

    @staticmethod
    def fix_date_filter(sql, question):
        m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', question)
        if m:
            exact_date = m.group(0)
            month_pattern = exact_date[:7]
            sql = re.sub(
                rf"date\s+LIKE\s*'{re.escape(month_pattern)}%'",
                f"date = '{exact_date}'",
                sql, flags=re.IGNORECASE,
            )
            sql = re.sub(
                rf"date\s*>=\s*'{exact_date}'\s+AND\s+date\s*<=\s*'{exact_date}'",
                f"date = '{exact_date}'",
                sql, flags=re.IGNORECASE,
            )
        if re.search(r'\b(?:this\s+month|last\s+month|current\s+month)\b', question, re.IGNORECASE):
            sql = re.sub(
                r"date\s*=\s*'(\d{4})-(\d{2})-\d{2}'",
                r"date LIKE '\1-\2%'",
                sql, flags=re.IGNORECASE,
            )
        if re.search(r'\btoday\b', question, re.IGNORECASE):
            today_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            sql = re.sub(
                r"date\s*=\s*'\d{4}-\d{2}-\d{2}'",
                f"date = '{today_str}'",
                sql, flags=re.IGNORECASE,
            )
            sql = re.sub(
                r"date\s+LIKE\s*'\d{4}-\d{2}%'",
                f"date = '{today_str}'",
                sql, flags=re.IGNORECASE,
            )
        elif re.search(r'\byesterday\b|\blast\s+(?:day|date|night|evening|morning|afternoon)\b', question, re.IGNORECASE):
            yesterday_str = (datetime.now(TIMEZONE) - timedelta(days=1)).strftime("%Y-%m-%d")
            sql = re.sub(
                r"date\s*=\s*'\d{4}-\d{2}-\d{2}'",
                f"date = '{yesterday_str}'",
                sql, flags=re.IGNORECASE,
            )
            sql = re.sub(
                r"date\s+LIKE\s*'\d{4}-\d{2}%'",
                f"date = '{yesterday_str}'",
                sql, flags=re.IGNORECASE,
            )
        return sql

    @staticmethod
    def fix_missing_date_filter(sql, question):
        q = question.lower()
        has_date = re.search(r'\bdate\s*(?:LIKE|=|>=|<=|>|<|BETWEEN)\b', sql, re.IGNORECASE)
        if has_date:
            return sql
        now = datetime.now(TIMEZONE)
        date_filter = None
        if re.search(r'\bthis\s+month\b', q):
            date_filter = f"date LIKE '{now.strftime('%Y-%m')}%'"
        elif re.search(r'\blast\s+month\b', q):
            last_month = (now.replace(day=1) - timedelta(days=1))
            date_filter = f"date LIKE '{last_month.strftime('%Y-%m')}%'"
        elif re.search(r'\bthis\s+week\b', q):
            start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
            end = (now + timedelta(days=6 - now.weekday())).strftime('%Y-%m-%d')
            date_filter = f"date >= '{start}' AND date <= '{end}'"
        elif re.search(r'\blast\s+week\b', q):
            end = (now - timedelta(days=now.weekday() + 1)).strftime('%Y-%m-%d')
            start = (now - timedelta(days=now.weekday() + 7)).strftime('%Y-%m-%d')
            date_filter = f"date >= '{start}' AND date <= '{end}'"
        elif re.search(r'\bthis\s+year\b', q):
            date_filter = f"date LIKE '{now.strftime('%Y')}%'"
        elif re.search(r'\blast\s+year\b', q):
            date_filter = f"date LIKE '{now.year - 1}%'"
        elif re.search(r'\btoday\b', q):
            date_filter = f"date = '{now.strftime('%Y-%m-%d')}'"
        elif re.search(r'\byesterday\b', q):
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            date_filter = f"date = '{yesterday}'"
        if not date_filter:
            return sql
        sql = re.sub(
            r'(\bWHERE\b)',
            f'\\1 {date_filter} AND ',
            sql, count=1, flags=re.IGNORECASE,
        )
        return sql

    @staticmethod
    def fix_show_expenses_aggregate(sql, question):
        q = question.lower()
        show_intent = bool(re.search(r'\b(?:show|list|display)\b', q)) or \
                      bool(re.search(r'\bwhat\s+(?:are|were|is|was)\b.*\b(?:expense|transaction|record)', q))
        item_intent = bool(re.search(r'\b(?:which\s+(?:date|day)|when)\b', q)) and \
                      bool(re.search(r'\b(?:bought|buy|purchase|purchased|get|got)\b', q))
        if not show_intent and not item_intent:
            return sql
        if show_intent:
            if not re.search(r'\b(?:expense|expenses|transaction|transactions|record|records)\b', q):
                return sql
            if re.search(r'\b(?:how\s+much|total|sum|amount|spent|spend)\b', q):
                return sql
        if not re.search(r'\b(?:SUM|COUNT|AVG|COALESCE)\s*\(', sql, re.IGNORECASE):
            return sql
        if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
            return sql
        parts = re.split(r'\bFROM\b', sql, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) < 2:
            return sql
        return f"SELECT id, date, description, category, amount FROM {parts[1].strip()}"

    @staticmethod
    def _extract_item_keyword(q):
        for pattern in [
            r'\b(?:bought|buy|purchase|purchased|get|got)\s+(?:a\s+|an\s+|the\s+|some\s+)?(\w+(?:\s+\w+)?)',
            r'\b(?:spent|spend)\s+on\s+(?:a\s+|an\s+|the\s+)?(\w+(?:\s+\w+)?)',
            r'\bhow\s+much\s+(?:on|for)\s+(?:a\s+|an\s+|the\s+)?(\w+(?:\s+\w+)?)',
            r'(\w+(?:\s+\w+)?)\s+expenses?',
        ]:
            m = re.search(pattern, q)
            if m:
                phrase = m.group(1).strip().lower()
                parts = phrase.split()
                while parts and parts[0] in _SKIP_WORDS:
                    parts.pop(0)
                if parts and not re.match(r'\d+(?:st|nd|rd|th)$', parts[0]):
                    valid = [parts[0]]
                    for p in parts[1:]:
                        if p in _SKIP_WORDS or re.match(r'\d+(?:st|nd|rd|th)$', p):
                            break
                        valid.append(p)
                    return ' '.join(valid)
        return None

    @staticmethod
    def fix_description_filter(sql, question):
        q = question.lower()
        if has_condition(sql, "description LIKE") or has_condition(sql, "LOWER(description) LIKE"):
            return sql
        keyword = SqlService._extract_item_keyword(q)
        if not keyword or len(keyword) < 2 or keyword in [c.lower() for c in _ALL_CATEGORIES] or keyword.endswith('est'):
            return sql
        words = keyword.lower().split()
        clauses = []
        for w in words:
            safe = re.sub(r'[^\w\s]', '', w).replace('%', '').replace('_', '')[:50]
            clauses.append(f"LOWER(description) LIKE '%{safe}%'")
        if not clauses:
            return sql
        return add_condition(sql, " AND ".join(clauses))

    @staticmethod
    def fix_aggregate_sql(sql, question):
        q = question.lower()
        if not re.search(r'\b(?:how\s+much|total|sum|amount)\b', q):
            return sql
        if re.search(r'\b(?:SUM|COUNT|AVG|COALESCE)\s*\(', sql, re.IGNORECASE):
            return sql
        if re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE):
            return sql
        parts = re.split(r'\bFROM\b', sql, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) < 2:
            return sql
        from_clause = parts[1].strip()
        for kw in [' ORDER BY ', ' LIMIT ', ' OFFSET ']:
            pos = from_clause.upper().find(kw)
            if pos != -1:
                from_clause = from_clause[:pos]
        return f"SELECT COALESCE(SUM(amount), 0) as total FROM {from_clause}"

    @staticmethod
    def fix_budget_query(sql, question):
        q = question.lower()
        if not re.search(r'\bbudget\b', q):
            return sql
        if 'budgets' in sql.lower():
            return sql
        month = datetime.now(TIMEZONE).strftime("%Y-%m")
        m = re.search(r"date\s+LIKE\s+'(\d{4}-\d{2})%'", sql)
        if m:
            month = m.group(1)
        mentioned_cat = None
        for cat in sorted(_ALL_CATEGORIES, key=len, reverse=True):
            if cat.lower() in q:
                mentioned_cat = cat
                break
        if mentioned_cat:
            return (
                f"SELECT b.category, b.amount as budget_amount, "
                f"COALESCE(SUM(e.amount), 0) as spent, "
                f"b.amount - COALESCE(SUM(e.amount), 0) as remaining "
                f"FROM budgets b "
                f"LEFT JOIN expenses e ON e.user_id = b.user_id AND e.category = b.category "
                f"AND e.date LIKE '{month}%' "
                f"WHERE b.user_id = :uid AND b.category = '{mentioned_cat}' "
                f"GROUP BY b.id, b.category, b.amount"
            )
        return (
            f"SELECT b.category, b.amount as budget_amount, "
            f"(SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{month}%') as spent, "
            f"(SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{month}%') as remaining "
            f"FROM budgets b WHERE b.user_id = :uid AND b.category = '__overall__'"
        )

    @staticmethod
    def _classify_intent(question):
        q = question.lower()
        return {
            "is_aggregate": bool(re.search(r'\b(?:how\s+much|total|sum|amount)\b', q)),
            "is_list": bool(re.search(r'\b(?:show|list|display|find|see|view)\b', q)),
            "is_breakdown": bool(re.search(r'\b(?:breakdown.*category|category.*breakdown|by\s+category|category\s+wise|which\s+category)\b', q)),
            "is_frequency": bool(re.search(r'\b(?:how\s+many|count|frequency|how\s+often)\b', q)),
            "is_most_expensive": bool(re.search(r'\b(?:most\s+expensive|biggest\s+expense|largest\s+expense)\b', q)),
            "is_top_n": bool(re.search(r'\b(top|first|biggest|largest)\s+\d+\b', q)),
            "is_ordinal": bool(re.search(r'\b(?:second|third|fourth|fifth|\d+(?:st|nd|rd|th))\b', q)),
            "is_budget": bool(re.search(r'\bbudget\b', q)),
            "has_sort_request": bool(re.search(r'\b(?:descending|desc|newest|reverse|sort|order)\b', q)),
        }

    @staticmethod
    def apply_all_fixes(sql, question):
        intent = SqlService._classify_intent(question)
        q = question.lower()

        # Phase 1: WHERE/filter fixers (non-conflicting, different parts of WHERE)
        sql = SqlService.fix_category_in_sql(sql, question)
        sql = SqlService.fix_description_filter(sql, question)
        sql = SqlService.fix_date_filter(sql, question)
        sql = SqlService.fix_missing_date_filter(sql, question)
        sql = SqlService.fix_history_id_filter(sql, question)

        # Phase 2: SELECT-modifying fixers (mutually exclusive — only one should win)
        if intent["is_budget"]:
            sql = SqlService.fix_budget_query(sql, question)
        elif intent["is_frequency"] and intent["is_breakdown"]:
            sql = SqlService.fix_frequency_sql(sql, question)
            if not re.search(r'\b(?:SUM|COUNT|GROUP\s+BY)\b', sql, re.IGNORECASE):
                sql = SqlService.fix_category_breakdown_sql(sql, question)
        elif intent["is_breakdown"]:
            sql = SqlService.fix_category_breakdown_sql(sql, question)
        elif intent["is_list"] and not intent["is_aggregate"]:
            sql = SqlService.fix_show_expenses_aggregate(sql, question)
        elif intent["is_aggregate"]:
            sql = SqlService.fix_aggregate_sql(sql, question)

        if intent["is_frequency"]:
            sql = SqlService.fix_frequency_sql(sql, question)

        # Phase 3: ORDER/LIMIT fixers (mutually exclusive per category)
        if intent["is_most_expensive"]:
            sql = SqlService.fix_most_expensive_sql(sql, question)
        elif intent["is_ordinal"]:
            sql = SqlService.fix_ordinal_limit(sql, question)
        elif intent["is_top_n"]:
            sql = SqlService.fix_top_n_limit(sql, question)

        sql = SqlService.fix_sort_order(sql, question)
        sql = SqlService.fix_sort_column(sql, question)

        # Phase 4: Syntax fixups (always safe)
        sql = SqlService.fix_limit_syntax(sql, question)

        return sql

    @staticmethod
    def validate_results(question, columns, rows):
        q = question.lower()
        issues = []

        col_set = {c.lower() for c in columns}
        has_amount = bool(col_set & {"total", "amount", "sum", "spent", "cost"})
        has_date = bool(col_set & {"date", "day"})
        has_category = bool(col_set & {"category"})
        has_description = bool(col_set & {"description", "desc"})
        has_count = "count" in col_set

        # Check: user asked "how much" but no amount column
        if re.search(r'\b(?:how\s+much|total|spent)\b', q) and not has_amount and not has_count:
            issues.append("question asks about spending but result has no amount column")

        # Check: user asked about a category but result has no category filter
        mentioned_cat = None
        for cat in _ALL_CATEGORIES:
            if cat.lower() in q:
                mentioned_cat = cat
                break
        if mentioned_cat and has_category:
            for row in rows:
                if row.get("category") and row["category"] != mentioned_cat:
                    issues.append(f"result includes category '{row['category']}' but question is about '{mentioned_cat}'")
                    break

        # Check: user asked for list but only got an aggregate
        list_intent = bool(re.search(r'\b(?:show|list|display|find|see)\b', q))
        expense_keywords = bool(re.search(r'\b(?:expense|transaction|record|item)\b', q))
        if list_intent and has_amount and not has_description and not has_category:
            if has_amount and len(columns) <= 2:
                issues.append("question asks to show/list but result is an aggregate (not individual rows)")

        # Check: user asked for items but only count returned
        if list_intent and has_count and not has_amount and not has_description:
            issues.append("question asks to list transactions but only count returned")

        # Check: empty results for time-specific questions
        if not rows and re.search(r'\b(?:this\s+month|last\s+month|today|yesterday)\b', q):
            issues.append("empty result for a time period that likely has data")

        return issues
