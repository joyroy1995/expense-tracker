import json
import re
from llm.config import _get_client, _has_api_key, FAST_MODEL, LLM_TIMEOUT
from llm.categories import CATEGORIES, CATEGORIES_STR
from llm.expenses import check_learned

SPLIT_PROMPT = f"""You are an expense splitter for a Bangladeshi user. Given a description containing multiple purchases, split it into individual items. Each item gets its own description, category, and amount.

Categories: {CATEGORIES_STR}

Rules:
- Split on separators: comma, "ar", "ও", "and", "+"
- Description must NOT contain the amount, "taka", "tk", "৳", or "টাকা"
- Description should be the item name only, but KEEP quantity modifiers (1 kg, 2 ta, 1 ltr, etc.)
- Amount must be a number only (no currency text)
- If the text is a single purchase, return it as one item
- If amount is missing from an item, split the total proportionally or set to 0

Examples:
Input: gorur mangsho 500 ar mach 300, rickshaw 50
Output: [{{"description":"gorur mangsho","category":"Groceries","amount":500}},
         {{"description":"mach","category":"Groceries","amount":300}},
         {{"description":"rickshaw","category":"Transport","amount":50}}]

Input: 1 kg gorur mangsho 600 tk ar 2 ta dim 30 taka
Output: [{{"description":"1 kg gorur mangsho","category":"Groceries","amount":600}},
         {{"description":"2 ta dim","category":"Groceries","amount":30}}]

Input: bazar korlam 1500
Output: [{{"description":"bazar korlam","category":"Groceries","amount":1500}}]

Input: rickshaw 30 ar bus 20 ar lunch 150
Output: [{{"description":"rickshaw","category":"Transport","amount":30}},
         {{"description":"bus","category":"Transport","amount":20}},
         {{"description":"lunch","category":"Dining Out","amount":150}}]

Return ONLY a valid JSON array. No explanation."""


def _clean_split_desc(desc):
    d = desc.strip()
    d = re.sub(r'\b\d+(?:\.\d+)?\s*(?:taka|tk|৳|টাকা)\s*$', '', d, flags=re.IGNORECASE).strip()
    d = re.sub(r'\b(?:taka|tk|৳|টাকা)\s*\d+(?:\.\d+)?\s*$', '', d, flags=re.IGNORECASE).strip()
    d = re.sub(r'\s*\d+(?:\.\d+)?\s*$', '', d).strip()
    return d


def split_expenses(description, learned_categories=None):
    if not _has_api_key():
        return None
    try:
        client = _get_client()
        if not client:
            print(f"[ERROR] Groq client not available for split_expenses", file=sys.stderr)
            return None
        response = client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": "You are an expense splitter. Return only a JSON array."},
                {"role": "user", "content": f"{SPLIT_PROMPT}\n\nInput: {description}\nOutput:"},
            ],
            temperature=0.1,
            timeout=LLM_TIMEOUT,
        )
        text = response.choices[0].message.content.strip().strip("```").strip()
        if text.startswith("json"):
            text = text[4:].strip()
        items = json.loads(text)
        if not isinstance(items, list):
            return None
        for item in items:
            item["description"] = _clean_split_desc(item.get("description", ""))
            item["amount"] = float(item.get("amount", 0))
            cat = item.get("category", "Other")
            if cat not in CATEGORIES:
                for c in CATEGORIES:
                    if c.lower() in cat.lower():
                        cat = c
                        break
                else:
                    cat = "Other"
            item["category"] = cat
        if learned_categories:
            for item in items:
                learned_cat = check_learned(item.get("description", ""), learned_categories)
                if learned_cat:
                    item["category"] = learned_cat
        return items
    except Exception as e:
        print(f"[ERROR] split_expenses failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None
