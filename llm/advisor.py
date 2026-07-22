import json
import sys
import calendar
from datetime import datetime, date, timedelta
from collections import defaultdict
from llm.config import _get_client, _has_api_key, COMPLEX_MODEL, LLM_TIMEOUT
from config import CATEGORY_COLORS


FIXED_EXPENSE_CATEGORIES = {"Rent", "Bills"}

ADVISOR_PROMPT = """You are a personal finance advisor for a Bangladeshi user. Analyze their spending data and provide actionable advice.

Current month: {current_month} ({month_name} {year})
Days elapsed: {days_elapsed}/{days_in_month}

Spending Overview:
{category_breakdown}

Monthly Totals (Last 3 months):
{monthly_totals}

{budget_section}

{anomalies_section}

{fixed_categories_section}

{remaining_budget_section}

{recommendation_guidance}

Return ONLY valid JSON with this exact structure:
{{
  "recommendations": [
    {{
      "category": "CategoryName",
      "priority": "high" | "medium" | "low",
      "current_month": <number>,
      "three_month_avg": <number>,
      "delta_pct": <number>,
      "suggested_reduction_pct": <number>,
      "potential_savings": <number>,
      "reasoning": "<1-2 sentence actionable advice>",
      "tip": "<specific actionable tip>"
    }}
  ],
  "anomalies": [
    {{
      "category": "CategoryName",
      "amount": <number>,
      "typical": <number>,
      "reason": "<explanation>"
    }}
  ],
  "health_score": <0-100>,
  "health_label": "excellent" | "good" | "fair" | "poor",
  "remaining_budget_advice": {{
    "remaining_budget": <number or null>,
    "remaining_days": <number>,
    "daily_limit": <number or null>,
    "category_allocation": "<specific allocation advice for remaining budget>",
    "essential_priorities": ["category1", "category2"],
    "cut_recommended": ["category1", "category2"]
  }}
}}

Guidelines:
- health_score: 80+ excellent, 60-79 good, 40-59 fair, <40 poor. Base on budget adherence (most important), spending consistency, and anomaly presence. If the user has significantly exceeded their budget (>25% over), the score should NOT be excellent or good.
- Max 4 recommendations, sorted by priority (high first).
- Only flag anomalies if spending is >50% above the 3-month average AND the delta is >1000 BDT.
- delta_pct is the percentage ABOVE the average (e.g., if avg=5000 and current=7000, delta_pct=40).
- suggested_reduction_pct should be realistic (usually 10-30%).
- potential_savings = current_month * (suggested_reduction_pct / 100), rounded.
- Do not include categories with no spending.
- Keep reasoning concise and in English.
- Use ৳ symbol for amounts.
- CRITICAL: Never recommend reducing fixed/essential categories (listed above). These are non-negotiable expenses. Only mention them if there is an anomaly (overpayment or unusual spike).
- If remaining_budget info is provided, fill remaining_budget_advice with specific daily limit and allocation tips. If not provided, set remaining_budget and daily_limit to null.

Do not add any explanation or extra text. Return only the JSON."""


def _fmt_category_breakdown(category_totals, month_total):
    if not category_totals:
        return "No spending data for this month."
    lines = []
    for c in category_totals:
        pct = (c["total"] / month_total * 100) if month_total else 0
        lines.append(f"- {c['category']}: ৳{c['total']:,.0f} ({c['count']}x, {pct:.0f}%)")
    return "\n".join(lines)


def _fmt_monthly_totals(monthly_totals):
    if not monthly_totals:
        return "No historical data available."
    return "\n".join(
        f"- {m['month']}: ৳{m['total']:,.0f}" for m in monthly_totals
    )


def _detect_anomalies(category_totals, monthly_totals):
    anomalies = []
    if not category_totals or len(monthly_totals) < 2:
        return anomalies

    current_cats = {c["category"]: c["total"] for c in category_totals}

    older_totals = monthly_totals[1:]
    avg_by_cat = defaultdict(list)

    for mt in older_totals:
        if mt.get("breakdown"):
            for c in mt["breakdown"]:
                avg_by_cat[c["category"]].append(c["total"])

    for cat, current in current_cats.items():
        if cat not in avg_by_cat or len(avg_by_cat[cat]) < 2:
            continue
        avg = sum(avg_by_cat[cat]) / len(avg_by_cat[cat])
        if avg == 0:
            continue
        delta_pct = ((current - avg) / avg) * 100
        if delta_pct > 50 and (current - avg) > 1000:
            anomalies.append({
                "category": cat,
                "amount": round(current, 2),
                "typical": round(avg, 2),
                "reason": f"{delta_pct:.0f}% above normal — {'possible bulk purchase or special event' if delta_pct > 100 else 'significantly higher than usual'}",
            })
    return anomalies


def compute_health_score(recommendations, anomalies, monthly_totals, month_total=0, budget_amount=None):
    score = 80
    high_count = sum(1 for r in recommendations if r["priority"] == "high")
    score -= high_count * 10
    score -= len(anomalies) * 8

    if budget_amount and budget_amount > 0 and month_total > 0:
        overrun_pct = ((month_total - budget_amount) / budget_amount) * 100
        if overrun_pct > 50:
            score -= 30
        elif overrun_pct > 25:
            score -= 20
        elif overrun_pct > 10:
            score -= 10
        elif overrun_pct > 0:
            score -= 5

    if len(monthly_totals) >= 2:
        recent = monthly_totals[0]["total"]
        older = monthly_totals[-1]["total"]
        if older > 0:
            trend = ((recent - older) / older) * 100
            if trend > 20:
                score -= 10
            elif trend > 10:
                score -= 5

    score = max(0, min(100, score))
    if score >= 80:
        label = "excellent"
    elif score >= 60:
        label = "good"
    elif score >= 40:
        label = "fair"
    else:
        label = "poor"
    return score, label


def generate_analysis(category_totals, monthly_totals_with_breakdown, now=None, remaining_budget=None, budget_amount=None):
    if now is None:
        now = datetime.now()
    year, month = now.year, now.month
    month_name = now.strftime("%B")
    days_in_month = calendar.monthrange(year, month)[1]
    days_elapsed = min(now.day, days_in_month)
    remaining_days = max(0, days_in_month - days_elapsed)

    month_total = sum(c["total"] for c in category_totals) if category_totals else 0

    anomalies = _detect_anomalies(category_totals, monthly_totals_with_breakdown)
    anomaly_json = json.dumps(anomalies) if anomalies else "[]"

    has_high_spend = any(
        c["total"] > 5000 for c in category_totals
    ) if category_totals else False
    high_cats = [c for c in (category_totals or []) if c["total"] > 5000]

    rec_guidance = ""
    if high_cats:
        cat_names = ", ".join(c["category"] for c in high_cats[:3])
        rec_guidance = f"Focus on optimizing these high-spend categories: {cat_names}. Provide specific reduction advice."

    user_fixed_cats = FIXED_EXPENSE_CATEGORIES & {c["category"] for c in (category_totals or [])}
    fixed_cats_section = (
        f"Fixed/essential categories present in your spending (do NOT recommend reducing these): {', '.join(sorted(user_fixed_cats))}."
        if user_fixed_cats else "No fixed/essential categories with spending this month."
    )

    if budget_amount and budget_amount > 0:
        overrun_pct = ((month_total - budget_amount) / budget_amount) * 100
        budget_section = (
            f"Monthly budget: ৳{budget_amount:,.0f}\n"
            f"Total spent: ৳{month_total:,.0f}\n"
            f"Over/under budget: {overrun_pct:+.1f}%"
        )
    else:
        budget_section = "No budget set."

    if remaining_budget is not None and remaining_days > 0:
        daily_limit = remaining_budget / remaining_days
        remaining_budget_section = (
            f"Remaining budget for rest of month: ৳{remaining_budget:,.0f}\n"
            f"Days remaining: {remaining_days}\n"
            f"Daily spending limit: ৳{daily_limit:,.0f}/day\n\n"
            f"The user has ৳{remaining_budget:,.0f} left for {remaining_days} days (৳{daily_limit:,.0f}/day). "
            f"ADVISE on how to allocate this. Essential categories (groceries, transport) should be prioritized. "
            f"Non-essential categories (dining out, entertainment, shopping) should be cut. "
            f"Fill remaining_budget_advice with specific allocation guidance."
        )
    else:
        remaining_budget_section = ""

    cat_lines = _fmt_category_breakdown(category_totals, month_total)

    monthly_simple = [
        {"month": m["month"], "total": m["total"]}
        for m in monthly_totals_with_breakdown
    ]
    monthly_lines = _fmt_monthly_totals(monthly_simple)

    if _has_api_key():
        try:
            prompt = ADVISOR_PROMPT.format(
                current_month=f"{year}-{month:02d}",
                month_name=month_name,
                year=year,
                days_elapsed=days_elapsed,
                days_in_month=days_in_month,
                category_breakdown=cat_lines,
                monthly_totals=monthly_lines,
                budget_section=budget_section,
                anomalies_section=(
                    f"Anomalies detected:\n" + "\n".join(
                        f"- {a['category']}: ৳{a['amount']:,.0f} vs typical ৳{a['typical']:,.0f} ({a['reason']})"
                        for a in anomalies
                    ) if anomalies else "No significant anomalies detected."
                ),
                fixed_categories_section=fixed_cats_section,
                remaining_budget_section=remaining_budget_section,
                recommendation_guidance=rec_guidance,
            )

            client = _get_client()
            if not client:
                raise RuntimeError("Groq client not available")

            response = client.chat.completions.create(
                model=COMPLEX_MODEL,
                messages=[
                    {"role": "system", "content": "You are a financial advisor. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_completion_tokens=800,
                timeout=LLM_TIMEOUT,
            )
            text = response.choices[0].message.content.strip().strip("```").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
            result = json.loads(text)

            recommendations = result.get("recommendations", [])
            anomalies_result = result.get("anomalies", [])
            health_score = result.get("health_score", 50)
            health_label = result.get("health_label", "fair")
            remaining_budget_advice = result.get("remaining_budget_advice")

            # Filter out fixed/essential categories from recommendations (unless anomalous)
            anomaly_cats = {a["category"] for a in anomalies_result}
            recommendations = [
                r for r in recommendations
                if r["category"] not in FIXED_EXPENSE_CATEGORIES or r["category"] in anomaly_cats
            ]
        except Exception as e:
            print(f"[ERROR] Advisor LLM failed: {type(e).__name__}: {e}", file=sys.stderr)
            recommendations = _fallback_recommendations(category_totals, monthly_totals_with_breakdown, month_total)
            anomalies_result = anomalies
            health_score, health_label = compute_health_score(recommendations, anomalies_result, monthly_simple, month_total, budget_amount)
            remaining_budget_advice = None
    else:
        recommendations = _fallback_recommendations(category_totals, monthly_totals_with_breakdown, month_total)
        anomalies_result = anomalies
        health_score, health_label = compute_health_score(recommendations, anomalies_result, monthly_simple, month_total, budget_amount)
        remaining_budget_advice = None

    total_potential = sum(r.get("potential_savings", 0) for r in recommendations)

    # Build remaining budget section for non-LLM path
    if remaining_budget_advice is None and remaining_budget is not None and remaining_days > 0:
        daily_limit = remaining_budget / remaining_days
        # Determine which categories to prioritize or cut based on data
        essential = {"Groceries", "Transport", "Food", "Health"}
        non_essential = {"Dining Out", "Entertainment", "Shopping", "Gifts", "Travel"}
        cat_set = {c["category"] for c in (category_totals or [])}
        essential_priority = sorted(c for c in essential if c in cat_set and c not in FIXED_EXPENSE_CATEGORIES)
        cut_rec = sorted(c for c in non_essential if c in cat_set)
        remaining_budget_advice = {
            "remaining_budget": round(remaining_budget, 0),
            "remaining_days": remaining_days,
            "daily_limit": round(daily_limit, 0),
            "category_allocation": (
                f"With ৳{remaining_budget:,.0f} for {remaining_days} days, you can spend ~৳{daily_limit:,.0f}/day. "
                f"Prioritize {' and '.join(essential_priority) if essential_priority else 'essentials'} — "
                f"skip {' and '.join(cut_rec) if cut_rec else 'non-essentials'} entirely."
            ),
            "essential_priorities": essential_priority,
            "cut_recommended": cut_rec,
        }

    return {
        "health_score": health_score,
        "health_label": health_label,
        "total_potential_savings": round(total_potential, 0),
        "analysis_date": now.strftime("%Y-%m-%d %H:%M:%S"),
        "recommendations": recommendations,
        "anomalies": anomalies_result,
        "monthly_totals": monthly_simple,
        "remaining_budget_advice": remaining_budget_advice,
    }


def _fallback_recommendations(category_totals, monthly_totals, month_total):
    recommendations = []
    if not category_totals:
        return recommendations

    current_cats = {c["category"]: c["total"] for c in category_totals}

    avg_by_cat = defaultdict(list)
    for mt in monthly_totals[1:]:
        for c in mt.get("breakdown", []):
            avg_by_cat[c["category"]].append(c["total"])

    for c in category_totals:
        cat = c["category"]
        current = c["total"]
        if current <= 0:
            continue
        if cat in FIXED_EXPENSE_CATEGORIES:
            continue

        if cat in avg_by_cat and len(avg_by_cat[cat]) >= 2:
            avg = sum(avg_by_cat[cat]) / len(avg_by_cat[cat])
            if avg > 0:
                delta_pct = ((current - avg) / avg) * 100
            else:
                delta_pct = 0
        else:
            avg = current
            delta_pct = 0

        if delta_pct > 20 and current > 2000:
            priority = "high" if delta_pct > 50 else "medium" if delta_pct > 30 else "low"
            reduction = min(30, max(10, int(delta_pct / 2)))
            savings = round(current * reduction / 100, 0)
            recommendations.append({
                "category": cat,
                "priority": priority,
                "current_month": round(current, 2),
                "three_month_avg": round(avg, 2),
                "delta_pct": round(delta_pct, 0),
                "suggested_reduction_pct": reduction,
                "potential_savings": savings,
                "reasoning": f"Spending on {cat} is {delta_pct:.0f}% above your average. Reducing by {reduction}% could save ৳{savings:,.0f}/month.",
                "tip": f"Try tracking each {cat.lower()} purchase and identify non-essential items.",
                "color": CATEGORY_COLORS.get(cat, "#6b7280"),
            })

    return sorted(recommendations, key=lambda r: ["high", "medium", "low"].index(r["priority"]))[:4]


def generate_optimization_advice(user_id, category_totals, monthly_totals_with_breakdown):
    now = datetime.now()
    return generate_analysis(category_totals, monthly_totals_with_breakdown, now)
