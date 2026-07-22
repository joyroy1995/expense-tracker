import json
import sys
from datetime import datetime
from llm.config import _get_client, _has_api_key, COMPLEX_MODEL, LLM_TIMEOUT

SESSION_REASON_PROMPT = """You analyze expense patterns to group them into meaningful sessions and infer the reason/purpose. The user is a Bangladeshi who writes expenses in English, Bengali, or Banglish (Bengali written in English letters).

Given a list of expenses, determine if they belong to a single session and what the reason is.

Rules for grouping:
- Temporal proximity: expenses within 3 hours of each other may belong together
- Semantic similarity: same store/type of purchase (e.g., all groceries, all commute)
- Travel chain: consecutive transport expenses (rickshaw → bus → tempo) are one commute
- Meal + transport: if food is near transport in time, it may be part of the same outing

Understand Bangla/Banglish descriptions:
- "মুরগি", "murgi/murghi" = chicken → Groceries
- "গরুর মাংস", "gorur mangsho" = beef → Groceries
- "রিকশা", "rickshaw" = rickshaw fare → Transport/Commute
- "বাস", "bus" = bus fare → Transport/Commute
- "ভাত", "bhat", "rice" = rice/meal → Food
- "বাজার", "bazar" = grocery shopping → Groceries
- "ওষুধ", "oshudh", "pharmacy" = medicine → Medical/Health
- "কাপড়", "jama", "kapur" = clothes → Shopping
- "বিল", "bill" = utility bill → Bills
- "ভাড়া", "bhara", "rent" = rent → Rent
- "রেস্টুরেন্ট", "restaurant", "hotel" = eating out → Dining
- "ডিম", "dim" = egg → Groceries
- "চা", "cha" = tea → Food or Dining Out
- "লাঞ্চ", "lunch" = lunch → Dining Out or Food
- "তেল", "tel" = oil/cooking oil → Groceries
- "দুধ", "dudh" = milk → Groceries
- "কola", "kola" = banana → Fruits
- "aam", "আম" = mango → Fruits
- "পানি", "pani" = water → Food
- "কাচ্চি", "kacchi", "biryani" = biryani → Dining Out
- "ফুচকা", "fuchka" = street food → Dining Out

Write a CONCISE session_reason (1 sentence, 6-12 words) that captures the essence of the spending. Mention the key items bought and the context, but keep it short and scannable.

Good examples:
- "Bazar theke gorur mangsho, dim ar shobji."
- "Morning commute by rickshaw, bus, cha at canteen."
- "Lunch er kacchi biryani with colleagues."
- "Evening grocery restock from Swapno."
- "Pharmacy run for bhai er medicine."
- "Ei month er shopping: jama ar chador."
- "Evening family outing: pizza ar garlic bread."
- "Rannar shobji: murgi, begun, potol, kola."
- "Eid shopping: jama, sharee, sho kapur."
- "Night medicine ar ORSaline for fever."
- "Rickshaw ar bus e office, canteen e cha."
- "Kacchi Bhai te lunch with friends."
- "Bazar khoroch: gorur mangsho, mach, shobji."
- "Basa bhara for this month."
- "House rent for February."
- "Mess bhara ar utility."
- "Basha bhara ar current bill."
- "Bari bhara, electricity ar gas bill."
- "Mess er month khala: bhara + utility."

When a single expense is clearly a known category (Rent, Bills, Groceries, etc.), set reason_category to match that category directly.

Output the session_reason in English with natural Bangla/Banglish words mixed in.

Expenses to analyze:
{expenses_json}

Return ONLY valid JSON with this exact structure:
{{
  "session_reason": "<concise 1-line reason, 6-12 words>",
  "reason_category": "<one of: Groceries, Commute, Dining, Social, Medical, Shopping, Bills, Entertainment, Travel, Home, Errand, Work, Rent, Food, Fruits, Other>",
  "icon": "<single emoji that represents this session>",
  "expense_ids": [<list of expense IDs that belong to this session>],
  "total_amount": <sum of amounts>,
  "start_time": "<ISO datetime of first expense>",
  "end_time": "<ISO datetime of last expense>",
  "confidence": "high" | "medium" | "low"
}}

If the expenses seem unrelated or span multiple distinct purposes, set session_reason to "Multiple Activities" and use expense_ids to list all of them.

Do not add any explanation or extra text. Return only the JSON."""


def extract_session_reason(expenses):
    if not _has_api_key() or not expenses:
        return None

    prompt = SESSION_REASON_PROMPT.format(
        expenses_json=json.dumps(expenses, indent=2, default=str),
    )

    try:
        client = _get_client()
        if not client:
            print(f"[ERROR] Groq client not available for extract_session_reason", file=sys.stderr)
            return None
        response = client.chat.completions.create(
            model=COMPLEX_MODEL,
            messages=[
                {"role": "system", "content": "You are a personal finance analysis assistant. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_completion_tokens=300,
            timeout=LLM_TIMEOUT,
        )
        text = response.choices[0].message.content.strip().strip("```").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        result = json.loads(text)
        return {
            "session_reason": result.get("session_reason", "Multiple Activities"),
            "reason_category": result.get("reason_category", "Other"),
            "icon": result.get("icon", "📦"),
            "expense_ids": result.get("expense_ids", [e.get("id") for e in expenses]),
            "total_amount": result.get("total_amount", sum(e.get("amount", 0) for e in expenses)),
            "start_time": result.get("start_time", expenses[0].get("created_at", "")),
            "end_time": result.get("end_time", expenses[-1].get("created_at", "")),
            "confidence": result.get("confidence", "medium"),
        }
    except Exception as e:
        print(f"[ERROR] extract_session_reason failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None
