import json
import sys
from datetime import date as _d
from llm.config import _get_client, _has_api_key, COMPLEX_MODEL, LLM_TIMEOUT

FORECAST_PROMPT = """You are a personal finance forecasting assistant. Given the user's daily spending data, predict their end-of-month total.

Today: {today}
Current month: {current_month}
Days elapsed: {days_elapsed} / {days_in_month}
Spent so far: ৳{spent_so_far}

Current month daily totals (৳):
{current_daily_totals}

Previous month daily totals (৳):
{prev_month_daily_totals}

Previous month final total: ৳{prev_month_total}
2 months ago final total: ৳{two_months_ago_total}

Category breakdown this month:
{category_breakdown}

Known fixed monthly expenses from last month:
{known_monthly_expenses}

{overall_budget_line}
{status_line}

Guidance for best_case vs worst_case:
- best_case: optimistic estimate (lowest projected total — assumes frugal remaining days)
- worst_case: pessimistic estimate (highest projected total — assumes higher remaining spending)
- best_case MUST be strictly less than worst_case to show a meaningful range
- If spending is very stable, use a 5-10% spread between best_case and worst_case

Return ONLY valid JSON with this exact structure:
{{
  "projected": <number>,
  "confidence": "high" | "medium" | "low",
  "reasoning": "<1-2 sentence explanation mentioning which fixed expenses are accounted for or still pending>",
  "best_case": <number>,
  "worst_case": <number>,
  "notes": "<optional note about risk factors or patterns noticed>"
}}

Do not add any explanation or extra text. Return only the JSON."""


def generate_forecast(data):
    if not _has_api_key():
        return None

    today = _d.today().strftime("%B %d, %Y")
    current_month = _d.today().strftime("%B %Y")
    month_name = _d.today().strftime("%B")

    def fmt_daily(daily_list):
        if not daily_list:
            return "No data yet"
        return "\n".join(
            f"{month_name} {d['date'].split('-')[2].lstrip('0')}: {d['total']}"
            for d in daily_list
        )

    def fmt_daily_prev(daily_list, month_idx):
        if not daily_list:
            return "No data"
        entries = []
        for d in daily_list:
            parts = d["date"].split("-")
            m = int(parts[1])
            day = parts[2].lstrip("0")
            m_name = _d(2000, m, 1).strftime("%B")
            entries.append(f"{m_name} {day}: {d['total']}")
        return "\n".join(entries)

    def fmt_category(cat_list):
        if not cat_list:
            return "No data"
        return "\n".join(
            f"{c['category']}: ৳{c['total']} ({c['count']}x)"
            for c in cat_list
        )

    budget_line = ""
    if data.get("overall_budget") and data["overall_budget"] > 0:
        pct = round((data["spent_so_far"] / data["overall_budget"]) * 100, 1)
        budget_line = f"Overall budget: ৳{data['overall_budget']:,.0f} ({pct}% used)"

    status_line = ""
    if data.get("prev_month_total") and data["prev_month_total"] > 0:
        daily_avg = data["spent_so_far"] / data["days_elapsed"] if data["days_elapsed"] > 0 else 0
        linear_proj = round(daily_avg * data["days_in_month"])
        diff_pct = round((linear_proj - data["prev_month_total"]) / data["prev_month_total"] * 100, 1)
        direction = "higher" if diff_pct > 0 else "lower"
        status_line = f"Linear projection: ৳{linear_proj:,} ({abs(diff_pct)}% {direction} than last month)"

    known_monthly = data.get("known_monthly_expenses", {})
    pending_items = known_monthly.get("pending", [])
    recorded_items = known_monthly.get("recorded", [])
    known_lines = []
    for item in pending_items:
        known_lines.append(f"⏳ {item['description']} — ৳{item['amount']:,.0f} ({item['category']}) — NOT yet recorded this month")
    for item in recorded_items:
        known_lines.append(f"✅ {item['description']} — ৳{item['amount']:,.0f} ({item['category']}) — already recorded")
    if not known_lines:
        known_lines.append("No known fixed expenses detected (or first month of data)")

    prompt = FORECAST_PROMPT.format(
        today=today,
        current_month=current_month,
        days_elapsed=data["days_elapsed"],
        days_in_month=data["days_in_month"],
        spent_so_far=data["spent_so_far"],
        current_daily_totals=fmt_daily(data.get("current_daily_totals", [])),
        prev_month_daily_totals=fmt_daily_prev(data.get("prev_month_daily_totals", []), 1),
        prev_month_total=data.get("prev_month_total", 0),
        two_months_ago_total=data.get("two_months_ago_total", 0),
        category_breakdown=fmt_category(data.get("category_breakdown", [])),
        known_monthly_expenses="\n".join(known_lines),
        overall_budget_line=budget_line,
        status_line=status_line,
    )

    try:
        client = _get_client()
        if not client:
            print(f"[ERROR] Groq client not available for generate_forecast", file=sys.stderr)
            return None
        response = client.chat.completions.create(
            model=COMPLEX_MODEL,
            messages=[
                {"role": "system", "content": "You are a financial forecasting assistant. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_completion_tokens=300,
            timeout=LLM_TIMEOUT,
        )
        text = response.choices[0].message.content.strip().strip("```").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        result = json.loads(text)
        return {
            "projected": result.get("projected"),
            "confidence": result.get("confidence", "medium"),
            "reasoning": result.get("reasoning", ""),
            "best_case": result.get("best_case"),
            "worst_case": result.get("worst_case"),
            "notes": result.get("notes", ""),
        }
    except Exception as e:
        print(f"[ERROR] generate_forecast failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None
