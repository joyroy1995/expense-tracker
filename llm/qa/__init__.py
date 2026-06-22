import json
import calendar
from datetime import date as _d, timedelta
from llm.config import _get_client, _has_api_key


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


SQL_PROMPT = """You are a SQL query generator for a personal expense tracker. Given a user's natural language question and the current date, generate a SQL query to answer it.

Current date: {today}
This month: {current_month}
Last month: {last_month}

Database schema:
{schema}

Rules:
1. Return ONLY the SQL query — no explanation, no markdown formatting, no backticks.
2. Use ONLY SELECT queries.
3. Always include "user_id = :uid" in the WHERE clause.
4. Use only conditions from the current question. The conversation history is provided for context about the user's previous questions only — do NOT carry over WHERE conditions (such as id != N, category filters, date filters, or any other clause) from history into the current query unless the current question explicitly repeats or implies them.
5. For date filtering:
   - Use LIKE with pattern: date LIKE '{current_month}%'
   - Use SUBSTR(date, 1, 4) for year extraction
   - Use SUBSTR(date, 1, 7) for year-month extraction
   - For date ranges use date >= 'YYYY-MM-DD' AND date <= 'YYYY-MM-DD'
   - Pre-computed relative dates — use as literal strings: today={today}, 7_days_ago={seven_days_ago}, week_start={week_start}, last_week_start={last_week_start}
    - Pre-computed date helpers for pacing: days_elapsed={days_elapsed}, days_in_month={days_in_month}
6. Column names: id, date, description, amount, category, user_id, created_at
7. Use COALESCE for safe SUM/AVG aggregates.
8. Limit results to 50 rows max unless the user asks for a specific number.
9. Use single quotes for strings.
10. For the budgets table: amounts are monthly budgets, one row per category. Compare actual spending vs budget using LEFT JOIN and GROUP BY. Exception: for '__overall__' budget (total spending across ALL categories), use a scalar subquery instead of a JOIN on category.
11. For description search, use LIKE with %% wildcards: description LIKE '%%keyword%%'
12. When comparing periods, use SUBSTR(date, 1, 7) in GROUP BY or WHERE.
13. For frequency/count questions ("how many times", "most used category", "in terms of frequency", "how often"), use COUNT(*) instead of SUM(amount). If the user asks which category by frequency, use COUNT(*) as count and ORDER BY count DESC.
14. Use portable SQL with string-based date comparisons — avoid database-specific functions like `date()` or `strftime()`.

Examples:

Q: How much on Transport this month?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND category = 'Transport' AND date LIKE '{current_month}%'

Q: Show all my Dining Out expenses from last month
SQL: SELECT date, description, amount FROM expenses WHERE user_id = :uid AND category = 'Dining Out' AND date LIKE '{last_month}%' ORDER BY date

Q: What categories did I spend on this month?
SQL: SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category ORDER BY total DESC

Q: How much did I spend between 2025-06-01 and 2025-06-15?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date >= '2025-06-01' AND date <= '2025-06-15'

Q: How much did I spend in the last 7 days?
SQL: SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date >= '{seven_days_ago}'

Q: List last 7 days expenses descending by date
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date >= '{seven_days_ago}' ORDER BY date DESC LIMIT 50

Q: What did I spend on 2025-06-15?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date = '2025-06-15'

Q: How much did I spend each day this month?
SQL: SELECT date, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY date ORDER BY date

Q: How much did I spend each month this year?
SQL: SELECT SUBSTR(date, 1, 7) as month, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_year}%' GROUP BY SUBSTR(date, 1, 7) ORDER BY month

Q: What was my most expensive expense this month?
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount DESC LIMIT 1

Q: What was my smallest expense this month?
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount ASC LIMIT 1

Q: Average daily spending this month
SQL: SELECT COALESCE(AVG(daily.total), 0) as avg_daily FROM (SELECT SUM(amount) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY date) daily

Q: Am I on track with my spending this month?
SQL: SELECT COALESCE(SUM(amount), 0) as total, ROUND(COALESCE(SUM(amount), 0) / {days_elapsed}, 0) as daily_avg, {days_elapsed} as days_elapsed, {days_in_month} as days_in_month FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%'

Q: How many times did I eat out this month?
SQL: SELECT COUNT(*) as count FROM expenses WHERE user_id = :uid AND category = 'Dining Out' AND date LIKE '{current_month}%'

Q: Which category did I use the most this month by frequency?
SQL: SELECT category, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category ORDER BY count DESC LIMIT 1

Q: How does this month compare to last month?
SQL: SELECT SUBSTR(date, 1, 7) as month, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND (date LIKE '{current_month}%' OR date LIKE '{last_month}%') GROUP BY SUBSTR(date, 1, 7) ORDER BY month

Q: How does this week compare to last week?
SQL: SELECT 'This week' as period, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date >= '{week_start}' AND date <= '{today}' UNION ALL SELECT 'Last week', COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date >= '{last_week_start}' AND date < '{week_start}'

Q: How does this year compare to last year?
SQL: SELECT SUBSTR(date, 1, 4) as year, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND (date LIKE '{current_year}%' OR date LIKE '{last_year}%') GROUP BY SUBSTR(date, 1, 4) ORDER BY year

Q: How much on Food and Transport combined this month?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND (category = 'Food' OR category = 'Transport') AND date LIKE '{current_month}%'

Q: Show expenses over 500 this month
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND amount > 500 AND date LIKE '{current_month}%' ORDER BY amount DESC

Q: Which categories did I spend more than 1000 on this month?
SQL: SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category HAVING total > 1000 ORDER BY total DESC

Q: Show me all expenses where I used Uber or Pathao
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND (description LIKE '%uber%' OR description LIKE '%pathao%') ORDER BY date DESC LIMIT 50

Q: How much did I spend on Uber this month?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND LOWER(description) LIKE '%uber%' AND date LIKE '{current_month}%'

Q: How much on groceries at Swapno this month?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND LOWER(description) LIKE '%swapno%' AND category = 'Groceries' AND date LIKE '{current_month}%'

Q: How much budget is left for Groceries this month?
SQL: SELECT b.category, b.amount as budget_amount, COALESCE(SUM(e.amount), 0) as spent, b.amount - COALESCE(SUM(e.amount), 0) as remaining FROM budgets b LEFT JOIN expenses e ON e.user_id = b.user_id AND e.category = b.category AND e.date LIKE '{current_month}%' WHERE b.user_id = :uid AND b.category = 'Groceries' GROUP BY b.id, b.category, b.amount

Q: Do I have budget left for Overall?
SQL: SELECT b.category, b.amount as budget_amount, (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%') as spent, b.amount - (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%') as remaining FROM budgets b WHERE b.user_id = :uid AND b.category = '__overall__'

Q: Show me all my budgets and how much I have spent
SQL: SELECT b.category, b.amount as budget_amount, COALESCE(e.spent, 0) as spent, b.amount - COALESCE(e.spent, 0) as remaining FROM budgets b LEFT JOIN (SELECT category, SUM(amount) as spent FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category) e ON e.category = b.category WHERE b.user_id = :uid ORDER BY b.category

Q: What are the top 5 categories I spend the most on this year?
SQL: SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_year}%' GROUP BY category ORDER BY total DESC LIMIT 5

Q: Show top 5 expenses this month
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount DESC LIMIT 5

Q: Show all expenses from this week
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date >= '{week_start}' AND date <= '{today}' ORDER BY date

Q: What was my largest expense last month?
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{last_month}%' ORDER BY amount DESC LIMIT 1

Q: What was my second most expensive expense this month?
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount DESC LIMIT 1 OFFSET 1

Q: Which day did I spend the most this month?
SQL: SELECT date, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY date ORDER BY total DESC LIMIT 1

Q: What's my total spending this year so far?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_year}%'

Q: How much in January 2025?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '2025-01%'

{history}
Q: {question}
SQL:"""


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


def generate_sql(question, schema, history=None, retries=1):
    if not _has_api_key():
        return None
    today, current_month, last_month, current_year, seven_days_ago, week_start, last_week_start, days_elapsed, days_in_month, last_year = _fmt_dates()
    hist_text = _fmt_history(history, max_entries=3)
    prompt = SQL_PROMPT.format(
        today=today, current_month=current_month, last_month=last_month,
        current_year=current_year, last_year=last_year,
        seven_days_ago=seven_days_ago,
        week_start=week_start, last_week_start=last_week_start,
        days_elapsed=days_elapsed, days_in_month=days_in_month,
        schema=schema, question=question, history=hist_text,
    )
    last_error = None
    for attempt in range(retries + 1):
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a SQL query generator. Return only the SQL query."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=250,
            )
            sql = response.choices[0].message.content.strip().strip("```").strip()
            if sql.lower().startswith("sql"):
                sql = sql[3:].strip()
            if sql.upper().startswith("SELECT") and "user_id = :uid" in sql:
                return sql
            if attempt < retries:
                prompt += "\n\nThe previous SQL was invalid. Make sure it starts with SELECT and includes user_id = :uid in the WHERE clause."
            else:
                last_error = "Generated SQL missing SELECT or :uid filter"
        except Exception as e:
            last_error = str(e)
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
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a SQL query fixer. Return only the corrected SQL."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        fixed = response.choices[0].message.content.strip().strip("```").strip()
        if fixed.lower().startswith("sql"):
            fixed = fixed[3:].strip()
        if fixed.upper().startswith("SELECT") and "user_id = :uid" in fixed:
            return fixed
        return None
    except Exception:
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
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a friendly Bangladeshi personal finance assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
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
