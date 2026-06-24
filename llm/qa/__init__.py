import json
import re
import calendar
import sys
from datetime import date as _d, timedelta
from llm.config import _get_client, _has_api_key, COMPLEX_MODEL, LLM_TIMEOUT


def _fmt_history(history, max_entries=6):
    if not history:
        return ""
    lines = ["\n---\nConversation history:"]
    for h in history[-max_entries:]:
        role = "User" if h["role"] == "user" else "Assistant"
        lines.append(f"{role}: {h['content']}")
    lines.append("---")
    return "\n".join(lines)


def _fmt_dates():
    today = _d.today()
    ym = today.strftime("%Y-%m")
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    seven_days_ago = (today - timedelta(days=7)).isoformat()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    last_week_start = (today - timedelta(days=today.weekday() + 7)).isoformat()
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    last_year = str(today.year - 1)
    return today.isoformat(), ym, prev, today.strftime("%Y"), seven_days_ago, week_start, last_week_start, days_elapsed, days_in_month, last_year


_EXAMPLE_BUCKETS = {
    "aggregate": [
        ("How much on Transport this month?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND category = 'Transport' AND date LIKE '{current_month}%'"),
        ("How much did I spend in the last 7 days?", "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date >= '{seven_days_ago}'"),
        ("What did I spend on 2025-06-15?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date = '2025-06-15'"),
        ("What's my total spending this year so far?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_year}%'"),
    ],
    "list": [
        ("Show all my Dining Out expenses from last month", "SELECT date, description, amount FROM expenses WHERE user_id = :uid AND category = 'Dining Out' AND date LIKE '{last_month}%' ORDER BY date"),
        ("List last 7 days expenses descending by date", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date >= '{seven_days_ago}' ORDER BY date DESC LIMIT 50"),
        ("Show all expenses from this week", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date >= '{week_start}' AND date <= '{today}' ORDER BY date"),
    ],
    "breakdown": [
        ("What categories did I spend on this month?", "SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category ORDER BY total DESC"),
        ("How much did I spend each day this month?", "SELECT date, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY date ORDER BY date"),
        ("How much did I spend each month this year?", "SELECT SUBSTR(date, 1, 7) as month, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_year}%' GROUP BY SUBSTR(date, 1, 7) ORDER BY month"),
        ("Which day did I spend the most this month?", "SELECT date, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY date ORDER BY total DESC LIMIT 1"),
    ],
    "comparison": [
        ("How does this month compare to last month?", "SELECT SUBSTR(date, 1, 7) as month, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND (date LIKE '{current_month}%' OR date LIKE '{last_month}%') GROUP BY SUBSTR(date, 1, 7) ORDER BY month"),
        ("How does this week compare to last week?", "SELECT 'This week' as period, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date >= '{week_start}' AND date <= '{today}' UNION ALL SELECT 'Last week', COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date >= '{last_week_start}' AND date < '{week_start}'"),
        ("How does this year compare to last year?", "SELECT SUBSTR(date, 1, 4) as year, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND (date LIKE '{current_year}%' OR date LIKE '{last_year}%') GROUP BY SUBSTR(date, 1, 4) ORDER BY year"),
    ],
    "extreme": [
        ("What was my most expensive expense this month?", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount DESC LIMIT 1"),
        ("What was my smallest expense this month?", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount ASC LIMIT 1"),
        ("What was my second most expensive expense this month?", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount DESC LIMIT 1 OFFSET 1"),
    ],
    "frequency": [
        ("How many times did I eat out this month?", "SELECT COUNT(*) as count FROM expenses WHERE user_id = :uid AND category = 'Dining Out' AND date LIKE '{current_month}%'"),
        ("Which category did I use the most this month by frequency?", "SELECT category, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category ORDER BY count DESC LIMIT 1"),
    ],
    "budget": [
        ("How much budget is left for Groceries this month?", "SELECT b.category, b.amount as budget_amount, COALESCE(SUM(e.amount), 0) as spent, b.amount - COALESCE(SUM(e.amount), 0) as remaining FROM budgets b LEFT JOIN expenses e ON e.user_id = b.user_id AND e.category = b.category AND e.date LIKE '{current_month}%' WHERE b.user_id = :uid AND b.category = 'Groceries' GROUP BY b.id, b.category, b.amount"),
        ("Do I have budget left for Overall?", "SELECT b.category, b.amount as budget_amount, (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%') as spent, b.amount - (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%') as remaining FROM budgets b WHERE b.user_id = :uid AND b.category = '__overall__'"),
        ("Show me all my budgets and how much I have spent", "SELECT b.category, b.amount as budget_amount, COALESCE(e.spent, 0) as spent, b.amount - COALESCE(e.spent, 0) as remaining FROM budgets b LEFT JOIN (SELECT category, SUM(amount) as spent FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category) e ON e.category = b.category WHERE b.user_id = :uid ORDER BY b.category"),
    ],
    "threshold": [
        ("Show expenses over 500 this month", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND amount > 500 AND date LIKE '{current_month}%' ORDER BY amount DESC"),
        ("Which categories did I spend more than 1000 on this month?", "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category HAVING total > 1000 ORDER BY total DESC"),
    ],
    "description_search": [
        ("Show me all expenses where I used Uber or Pathao", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND (description LIKE '%uber%' OR description LIKE '%pathao%') ORDER BY date DESC LIMIT 50"),
        ("How much did I spend on Uber this month?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND LOWER(description) LIKE '%uber%' AND date LIKE '{current_month}%'"),
        ("How much on groceries at Swapno this month?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND LOWER(description) LIKE '%swapno%' AND category = 'Groceries' AND date LIKE '{current_month}%'"),
    ],
    "date_range": [
        ("How much did I spend between 2025-06-01 and 2025-06-15?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date >= '2025-06-01' AND date <= '2025-06-15'"),
    ],
    "general": [
        ("Average daily spending this month", "SELECT COALESCE(AVG(daily.total), 0) as avg_daily FROM (SELECT SUM(amount) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY date) daily"),
        ("Am I on track with my spending this month?", "SELECT COALESCE(SUM(amount), 0) as total, ROUND(CAST(COALESCE(SUM(amount), 0) / {days_elapsed} AS numeric), 0) as daily_avg, {days_elapsed} as days_elapsed, {days_in_month} as days_in_month FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%'"),
        ("Show top 5 expenses this month", "SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount DESC LIMIT 5"),
        ("What are the top 5 categories I spend the most on this year?", "SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_year}%' GROUP BY category ORDER BY total DESC LIMIT 5"),
        ("How much on Food and Transport combined this month?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND (category = 'Food' OR category = 'Transport') AND date LIKE '{current_month}%'"),
        ("How much in January 2025?", "SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '2025-01%'"),
    ],
}


def _classify_question(question):
    q = question.lower()
    buckets = []
    if re.search(r'\bbudget\b', q):
        buckets.append("budget")
    if re.search(r'\b(?:how\s+much|total|sum|spent)\b', q) and not re.search(r'\b(?:budget|compare|vs|versus)\b', q):
        buckets.append("aggregate")
    if re.search(r'\b(?:show|list|display|find)\b', q) and re.search(r'\b(?:expense|transaction|record)\b', q):
        buckets.append("list")
    if re.search(r'\b(?:breakdown|category\s+wise|per\s+category|each\s+day|per\s+day|by\s+category)\b', q):
        buckets.append("breakdown")
    if re.search(r'\b(?:compare|vs|versus)\b', q):
        buckets.append("comparison")
    if re.search(r'\b(?:most\s+expensive|biggest\s+expense|smallest|cheapest|largest\s+expense)\b', q):
        buckets.append("extreme")
    if re.search(r'\b(?:how\s+many|frequency|how\s+often|count)\b', q):
        buckets.append("frequency")
    if re.search(r'\b(?:over|above|more\s+than|under|below|less\s+than|exceeding)\s+\d+\b', q):
        buckets.append("threshold")
    if re.search(r'\b(?:uber|pathao|swapno|description|item|product|bought|purchase)\b', q):
        buckets.append("description_search")
    if re.search(r'\bbetween\b', q):
        buckets.append("date_range")
    if not buckets:
        buckets.append("general")
    return buckets


def _select_examples(question_buckets, fmt):
    seen_questions = set()
    selected = []
    for bucket in question_buckets:
        for q, sql in _EXAMPLE_BUCKETS.get(bucket, []):
            if q not in seen_questions:
                seen_questions.add(q)
                selected.append((q, sql))
                if len(selected) >= 4:
                    break
        if len(selected) >= 4:
            break
    if len(selected) < 2 and "general" not in question_buckets:
        for q, sql in _EXAMPLE_BUCKETS.get("general", []):
            if q not in seen_questions:
                seen_questions.add(q)
                selected.append((q, sql))
                if len(selected) >= 3:
                    break
    if fmt == "prompt":
        lines = []
        for q, sql in selected:
            lines.append(f"Q: {q}")
            lines.append(f"SQL: {sql}")
            lines.append("")
        return "\n".join(lines).strip()
    return selected


SQL_PROMPT_TEMPLATE = """You are a SQL query generator for a personal expense tracker. Given a user's natural language question and the current date, generate a SQL query to answer it.

Current date: {today}
This month: {current_month}
Last month: {last_month}

Database schema:
{schema}

Rules:
1. Return ONLY the SQL query — no explanation, no markdown formatting, no backticks.
2. Use ONLY SELECT queries.
3. Always include "user_id = :uid" in the WHERE clause.
4. Use only conditions from the current question. Do NOT carry over conditions from conversation history unless the current question explicitly repeats them.
5. For date filtering use LIKE for month patterns, SUBSTR for year/month extraction, and direct comparisons for exact dates.
6. Column names: id, date, description, amount, category, user_id, created_at
7. Use COALESCE for safe SUM/AVG aggregates. Limit results to 50 max.
8. For budgets: compare spending vs budget using LEFT JOIN and GROUP BY. For '__overall__', use a scalar subquery.
9. For description search: use LOWER(description) LIKE '%%keyword%%'
10. For frequency questions: use COUNT(*) instead of SUM(amount).
11. Pre-computed dates: today={today}, 7_days_ago={seven_days_ago}, week_start={week_start}, last_week_start={last_week_start}, days_elapsed={days_elapsed}, days_in_month={days_in_month}

Examples:
{examples}

{history}
Q: {question}
SQL:"""


VERIFY_SQL_PROMPT = """You are a SQL query verifier. Given a user's question and a generated SQL query, determine if the SQL correctly answers the question.

Question: {question}
Generated SQL: {sql}

Check in this order:
1. Does the SQL include user_id = :uid? This is MANDATORY — every query filters by current user. Even "all expenses" means "all of MY expenses". If :uid is missing, return {{"correct": false, "reason": "Missing user_id = :uid filter"}}.
2. Does the SELECT clause make sense? Aggregate (SUM/COUNT/AVG) for totals, columns for lists.
3. Are the filters appropriate? The SQL should only filter by things the user mentioned.

Return ONLY JSON: {{"correct": true}} or {{"correct": false, "reason": "..."}}
"""

ANSWER_PROMPT = """You are a friendly Bangladeshi personal finance assistant. Today is {today}.

Given a user's question, the SQL query used, and the results, provide a clear and concise natural language answer.

Question: {question}
SQL: {sql}
Results: {results}{history}

Rules:
- Provide a concise 1-3 sentence answer in English.
- If results are empty, say so politely.
- Use ৳ symbol for BDT amounts.
- Round amounts to 2 decimal places.
- For comparison questions, mention the actual values being compared.
- For budget questions, mention remaining or overspent amount if relevant.
- Be specific and helpful (mention category names, dates, amounts).
- Do NOT mention SQL or technical details unless the user specifically asks.

Answer:"""


CORRECT_SQL_PROMPT = """The SQL query below failed to execute. Fix it based on the error message.
Return ONLY the corrected SQL query — no explanation, no backticks.

Original SQL: {sql}
Error: {error}
Database schema:
{schema}
Original question: {question}{history}

Rules:
- Return only the corrected SQL query
- Must be a SELECT statement
- Must include user_id = :uid in the WHERE clause
- Use SQLite-compatible syntax

Corrected SQL:"""


def _verify_sql(sql, question):
    if not _has_api_key():
        return True
    q = question.replace("{", "").replace("}", "")
    s = sql.replace("{", "").replace("}", "")
    prompt = VERIFY_SQL_PROMPT.format(question=q, sql=s)
    try:
        client = _get_client()
        if not client:
            print(f"[ERROR] Groq client not available for _verify_sql", file=sys.stderr)
            return True
        response = client.chat.completions.create(
            model=COMPLEX_MODEL,
            messages=[
                {"role": "system", "content": "You are a SQL verifier. Return only JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=100,
            timeout=LLM_TIMEOUT,
        )
        text = response.choices[0].message.content.strip().strip("```").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        import json
        result = json.loads(text)
        return result.get("correct", True)
    except Exception as e:
        print(f"[ERROR] _verify_sql failed: {type(e).__name__}: {e}", file=sys.stderr)
        return True


def generate_sql(question, schema, history=None, retries=1):
    if not _has_api_key():
        return None
    fmt = _fmt_dates()
    today, current_month, last_month, current_year, seven_days_ago, week_start, last_week_start, days_elapsed, days_in_month, last_year = fmt
    hist_text = _fmt_history(history, max_entries=3)

    buckets = _classify_question(question)
    examples_text = _select_examples(buckets, "prompt")

    prompt = SQL_PROMPT_TEMPLATE.format(
        today=today, current_month=current_month, last_month=last_month,
        current_year=current_year, last_year=last_year,
        seven_days_ago=seven_days_ago,
        week_start=week_start, last_week_start=last_week_start,
        days_elapsed=days_elapsed, days_in_month=days_in_month,
        schema=schema, question=question, history=hist_text,
        examples=examples_text,
    )
    last_error = None
    for attempt in range(retries + 1):
        try:
            client = _get_client()
            if not client:
                print(f"[ERROR] Groq client not available for generate_sql", file=sys.stderr)
                raise RuntimeError("Groq client not available")
            response = client.chat.completions.create(
                model=COMPLEX_MODEL,
                messages=[
                    {"role": "system", "content": "You are a SQL query generator. Return only the SQL query."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=250,
                timeout=LLM_TIMEOUT,
            )
            sql = response.choices[0].message.content.strip().strip("```").strip()
            if sql.lower().startswith("sql"):
                sql = sql[3:].strip()
            if sql.upper().startswith("SELECT") and "user_id = :uid" in sql:
                if attempt == 0:
                    is_valid = _verify_sql(sql, question)
                    if not is_valid:
                        prompt += "\n\nThe SQL above has issues. Make sure it correctly filters by categories, dates, or amounts mentioned in the question. Generate a corrected SQL."
                        last_error = "Self-verification failed"
                        continue
                return sql
            if attempt < retries:
                prompt += "\n\nThe previous SQL was invalid. Make sure it starts with SELECT and includes user_id = :uid in the WHERE clause."
            else:
                last_error = "Generated SQL missing SELECT or :uid filter"
        except Exception as e:
            last_error = str(e)
            print(f"[ERROR] generate_sql attempt {attempt + 1}/{retries + 1} failed: {type(e).__name__}: {e}", file=sys.stderr)
            if attempt < retries:
                prompt += f"\n\nThere was an error: {last_error}. Please generate a corrected SQL query."
    if last_error:
        raise RuntimeError(f"SQL generation failed after {retries + 1} attempts: {last_error}")
    return None


def correct_sql(sql, error, schema, question, history=None):
    if not _has_api_key():
        return None
    hist_text = _fmt_history(history, max_entries=3)
    prompt = CORRECT_SQL_PROMPT.format(sql=sql, error=error, schema=schema, question=question, history=hist_text)
    try:
        client = _get_client()
        if not client:
            print(f"[ERROR] Groq client not available for correct_sql", file=sys.stderr)
            return None
        response = client.chat.completions.create(
            model=COMPLEX_MODEL,
            messages=[
                {"role": "system", "content": "You are a SQL query fixer. Return only the corrected SQL."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
            timeout=LLM_TIMEOUT,
        )
        fixed = response.choices[0].message.content.strip().strip("```").strip()
        if fixed.lower().startswith("sql"):
            fixed = fixed[3:].strip()
        if fixed.upper().startswith("SELECT") and "user_id = :uid" in fixed:
            return fixed
        return None
    except Exception as e:
        print(f"[ERROR] correct_sql failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def answer_from_results(question, sql, results, history=None):
    if not _has_api_key():
        return None
    today = _d.today().strftime("%B %d, %Y")
    results_str = json.dumps(results, indent=2, ensure_ascii=False)
    hist_text = _fmt_history(history)
    prompt = ANSWER_PROMPT.format(
        question=question, sql=sql, results=results_str,
        history=hist_text, today=today,
    )
    try:
        client = _get_client()
        if not client:
            print(f"[ERROR] Groq client not available for answer_from_results", file=sys.stderr)
            return None
        response = client.chat.completions.create(
            model=COMPLEX_MODEL,
            messages=[
                {"role": "system", "content": "You are a friendly Bangladeshi personal finance assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=300,
            timeout=LLM_TIMEOUT,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] answer_from_results failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None
        return None


def _display_cat(cat):
    if not cat:
        return ""
    if cat == "__overall__":
        return "Overall"
    return cat


def format_answer(columns, data, question):
    if not data:
        return {"text": "No expenses found matching your question.", "type": "text"}

    c_lower = [c.lower() for c in columns]
    amt_col = next((c for c in columns if c.lower() in ("total", "amount", "sum", "spent", "remaining")), None)
    cnt_col = next((c for c in columns if c.lower() in ("count", "cnt")), None)
    cat_col = next((c for c in columns if c.lower() == "category"), None)
    desc_col = next((c for c in columns if c.lower() in ("description", "desc")), None)
    date_col = next((c for c in columns if c.lower() == "date"), None)
    month_col = next((c for c in columns if c.lower() in ("month", "year_month")), None)
    avg_col = next((c for c in columns if c.lower() in ("avg", "average", "avg_daily")), None)
    max_col = next((c for c in columns if c.lower() in ("max", "maximum")), None)
    min_col = next((c for c in columns if c.lower() in ("min", "minimum")), None)
    remaining_col = next((c for c in columns if c.lower() == "remaining"), None)
    budget_col = next((c for c in columns if c.lower() in ("budget_amount", "budget")), None)
    days_elapsed_col = next((c for c in columns if c.lower() in ("days_elapsed",)), None)
    days_in_month_col = next((c for c in columns if c.lower() in ("days_in_month",)), None)
    daily_avg_col = next((c for c in columns if c.lower() in ("daily_avg",)), None)

    if remaining_col is not None and budget_col is not None:
        row = data[0]
        remaining = float(row.get(remaining_col, 0))
        budget = float(row.get(budget_col, 0))
        spent = float(row.get(amt_col, 0)) if amt_col else 0
        cat = _display_cat(row.get(cat_col, "")) if cat_col else ""
        pct = round((spent / budget * 100) if budget else 0, 0)
        if remaining > 0:
            text = f"You have ৳{remaining:.2f} remaining"
            if cat:
                text += f" for {cat}"
            text += f" (spent ৳{spent:.2f} of ৳{budget:.2f} budget)."
        elif remaining == 0:
            text = f"You have used your entire budget{' for ' + cat if cat else ''} (৳{budget:.2f})."
        else:
            text = f"You have exceeded your budget{' for ' + cat if cat else ''} by ৳{abs(remaining):.2f} (spent ৳{spent:.2f} of ৳{budget:.2f})."
        return {"text": text, "type": "budget", "spent": spent, "budget": budget, "remaining": remaining, "category": cat, "pct": pct}

    budget_amount_col = next((c for c in columns if c.lower() == "budget_amount"), None)

    if budget_amount_col is not None and daily_avg_col and days_elapsed_col and days_in_month_col and amt_col:
        row = data[0]
        total_spent = float(row.get(amt_col, 0))
        daily_avg = float(row.get(daily_avg_col, 0))
        de = int(row.get(days_elapsed_col, 1))
        dim = int(row.get(days_in_month_col, 30))
        projected = round(daily_avg * dim, 0)
        budget = float(row.get(budget_amount_col, 0))
        left_days = dim - de
        will_exceed = projected > budget if budget else None
        if budget:
            if will_exceed:
                text = f"At ৳{daily_avg:,.0f}/day you're on track to spend ৳{projected:,.0f} by end of month — exceeding your ৳{budget:,.0f} budget by ৳{projected - budget:,.0f}."
            else:
                text = f"At ৳{daily_avg:,.0f}/day you're on track to spend ৳{projected:,.0f} by end of month, well within your ৳{budget:,.0f} budget ({left_days} day(s) left)."
        else:
            text = f"Spent ৳{total_spent:,.0f} in {de} day(s) (avg: ৳{daily_avg:,.0f}/day). On track for ৳{projected:,.0f} by end of month ({left_days} day(s) left)."
        return {"text": text, "type": "forecast", "total": total_spent, "daily_avg": daily_avg, "projected": projected, "days_elapsed": de, "days_in_month": dim, "budget": budget, "will_exceed": will_exceed}

    if daily_avg_col and days_elapsed_col and days_in_month_col and amt_col:
        row = data[0]
        total_spent = float(row.get(amt_col, 0))
        daily_avg = float(row.get(daily_avg_col, 0))
        de = int(row.get(days_elapsed_col, 1))
        dim = int(row.get(days_in_month_col, 30))
        projected = round(daily_avg * dim, 0)
        left_days = dim - de
        if total_spent and daily_avg:
            text = f"Spent ৳{total_spent:,.0f} in {de} day(s) (avg: ৳{daily_avg:,.0f}/day). On track for ৳{projected:,.0f} by end of month ({left_days} day(s) left)."
        else:
            text = f"Spent ৳{total_spent:,.0f} in {de} day(s) this month."
        return {"text": text, "type": "pacing", "total": total_spent, "daily_avg": daily_avg, "projected": projected, "days_elapsed": de, "days_in_month": dim}

    if month_col and amt_col and len(data) >= 2:
        rows_sorted = sorted(data, key=lambda r: r.get(month_col, ""))
        months = []
        for r in rows_sorted:
            months.append({"label": r.get(month_col, ""), "amount": float(r.get(amt_col, 0))})
        label_strs = [f'{m["label"]} (৳{m["amount"]:.2f})' for m in months]
        text = "Monthly totals: " + ", ".join(label_strs) + "."
        return {"text": text, "type": "comparison", "months": months}

    if avg_col:
        avg = float(data[0].get(avg_col, 0))
        cnt_val = float(data[0].get(cnt_col, 0)) if cnt_col else 0
        if cnt_val:
            text = f"Average daily spending is ৳{avg:.2f} across {int(cnt_val)} day(s)."
        else:
            text = f"Average is ৳{avg:.2f}."
        return {"text": text, "type": "average", "avg": avg, "count": int(cnt_val) if cnt_val else 0}

    if len(data) == 1 and date_col and amt_col and not cat_col and not desc_col:
        row = data[0]
        date_val = row.get(date_col, "")
        total_val = float(row.get(amt_col, 0))
        return {"text": f"On {date_val} you spent ৳{total_val:.2f}.", "type": "date_spend", "date": date_val, "amount": total_val}

    if len(data) == 1 and not cat_col and not month_col:
        row = data[0]
        total = float(row.get(amt_col, 0)) if amt_col else None
        count = int(row.get(cnt_col, 0)) if cnt_col else None
        if total is not None and count is not None:
            return {"text": f"Your total is ৳{total:.2f} across {count} transaction(s).", "type": "total", "total": total, "count": count}
        if total is not None:
            return {"text": f"Your total is ৳{total:.2f}.", "type": "total", "total": total, "count": 0}
        if count is not None:
            return {"text": f"That's {count} transaction(s).", "type": "total", "total": 0, "count": count}

    if len(data) == 1 and desc_col and amt_col:
        row = data[0]
        desc = row.get(desc_col, "")
        amt_val = float(row.get(amt_col, 0))
        date_val = row.get(date_col, "") if date_col else ""
        text = f"It was ৳{amt_val:.2f} for \"{desc}\""
        if date_val:
            text += f" on {date_val}"
        text += "."
        return {"text": text, "type": "expense", "description": desc, "amount": amt_val, "date": date_val}

    if len(data) == 1 and (max_col or min_col):
        row = data[0]
        val = float(row.get(max_col or min_col, 0))
        desc = row.get(desc_col, "")
        cat = _display_cat(row.get(cat_col, ""))
        is_max = bool(max_col)
        suffix = f" ({desc})" if desc else f" in {cat}" if cat else ""
        label = "Most" if is_max else "Least"
        text = f"{label} expensive{suffix}: ৳{val:.2f}."
        return {"text": text, "type": "extremum", "value": val, "description": desc, "category": cat, "is_max": is_max}

    if cat_col and amt_col and len(data) == 2 and question and re.search(r'\b(more|less|than|vs)\b', question, re.IGNORECASE):
        rows_sorted = sorted(data, key=lambda r: float(r.get(amt_col, 0)), reverse=True)
        c1, a1 = _display_cat(rows_sorted[0].get(cat_col, "")), float(rows_sorted[0].get(amt_col, 0))
        c2, a2 = _display_cat(rows_sorted[1].get(cat_col, "")), float(rows_sorted[1].get(amt_col, 0))
        diff = abs(a1 - a2)
        more_less = "more" if a1 > a2 else "less"
        text = f"Spent ৳{a1:.2f} on {c1} vs ৳{a2:.2f} on {c2}. That's ৳{diff:.2f} {more_less} on {c1}."
        return {"text": text, "type": "comparison", "months": [{"label": c1, "amount": a1}, {"label": c2, "amount": a2}]}

    if cat_col and amt_col and len(data) > 1:
        total = sum(float(r.get(amt_col, 0)) for r in data)
        top = max(data, key=lambda r: float(r.get(amt_col, 0)))
        categories = []
        for r in data:
            cat_name = _display_cat(r.get(cat_col, ""))
            cat_amt = float(r.get(amt_col, 0))
            categories.append({"name": cat_name, "amount": cat_amt, "pct": round((cat_amt / total * 100) if total else 0, 1)})
        text = f"Total: ৳{total:.2f} across {len(data)} categories. Most spent on {_display_cat(top[cat_col])} (৳{float(top[amt_col]):.2f})."
        return {"text": text, "type": "category_breakdown", "total": total, "categories": categories}

    if cat_col and cnt_col and len(data) == 1:
        row = data[0]
        cat = row.get(cat_col, "")
        cnt = int(row.get(cnt_col, 0))
        return {"text": f"Most used category: {_display_cat(cat)} ({cnt} transaction(s)).", "type": "frequency", "category": _display_cat(cat), "count": cnt}

    total = sum(float(r.get(amt_col, 0)) for r in data) if amt_col else 0
    info = f" totaling ৳{total:.2f}" if amt_col else ""
    return {"text": f"Found {len(data)} result(s){info}.", "type": "list", "count": len(data), "total": total}
