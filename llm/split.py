import json
import re
import sys
from llm.config import _get_client, _has_api_key, FAST_MODEL, LLM_TIMEOUT
from llm.categories import CATEGORIES, CATEGORIES_STR, GROCERY_SUBCATEGORIES, GROCERY_SUBCATEGORIES_STR, extract_amount_fallback, keyword_category, grocery_subcategory
from llm.expenses import check_learned

SPLIT_PROMPT = f"""You are an expense splitter for a Bangladeshi user. Given a description containing multiple purchases, split it into individual items. Each item gets its own description, category, subcategory, and amount.

Categories: {CATEGORIES_STR}

Grocery subcategories: {GROCERY_SUBCATEGORIES_STR} (only set "subcategory" for Groceries items, e.g. murgi -> Meat, rui mach -> Fish, dim -> Dairy & Eggs, chal -> Rice & Grains; otherwise omit or set null)

Rules:
- Split on separators: comma, "ar", "ও", "and", "+"
- Description must NOT contain the amount, "taka", "tk", "৳", or "টাকা"
- Description should be the item name only, but KEEP quantity modifiers (1 kg, 2 ta, 1 ltr, etc.)
- Amount must be a number only (no currency text)
- If the text is a single purchase, return it as one item
- If amount is missing from an item, split the total proportionally or set to 0

Examples:
Input: gorur mangsho 500 ar mach 300, rickshaw 50
Output: [{{"description":"gorur mangsho","category":"Groceries","subcategory":"Meat","amount":500}},
         {{"description":"mach","category":"Groceries","subcategory":"Fish","amount":300}},
         {{"description":"rickshaw","category":"Transport","amount":50}}]

Input: 1 kg gorur mangsho 600 tk ar 2 ta dim 30 taka
Output: [{{"description":"1 kg gorur mangsho","category":"Groceries","subcategory":"Meat","amount":600}},
         {{"description":"2 ta dim","category":"Groceries","subcategory":"Dairy & Eggs","amount":30}}]

Input: bazar korlam 1500
Output: [{{"description":"bazar korlam","category":"Groceries","subcategory":"General","amount":1500}}]

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


def _set_subcategory(item):
    cat = item.get("category", "Other")
    if cat == "Groceries":
        item["subcategory"] = grocery_subcategory(item.get("description", ""))
    else:
        item.pop("subcategory", None)
    return item


def _simple_split_expenses(description, learned_categories=None):
    parts = re.split(r'\s*(?:,|\bar\b|\band\b|\u0993|\+)\s*', description)
    parts = [p.strip() for p in parts if p.strip()]
    items = []
    for part in parts:
        amount = extract_amount_fallback(part)
        if amount is None or amount <= 0:
            continue
        desc = _clean_split_desc(part)
        if not desc:
            continue
        cat = keyword_category(desc)
        items.append({"description": desc, "category": cat, "subcategory": grocery_subcategory(desc) if cat == "Groceries" else None, "amount": amount})
    if not items:
        return None
    if learned_categories:
        for item in items:
            learned_cat = check_learned(item.get("description", ""), learned_categories)
            if learned_cat:
                item["category"] = learned_cat
    for item in items:
        _set_subcategory(item)
    return items


def split_expenses(description, learned_categories=None):
    if _has_api_key():
        try:
            client = _get_client()
            if client:
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
                if isinstance(items, list):
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
                        if cat == "Groceries":
                            sub = item.get("subcategory")
                            if sub not in GROCERY_SUBCATEGORIES:
                                item["subcategory"] = grocery_subcategory(item.get("description", ""))
                        else:
                            item.pop("subcategory", None)
                    if learned_categories:
                        for item in items:
                            learned_cat = check_learned(item.get("description", ""), learned_categories)
                            if learned_cat:
                                item["category"] = learned_cat
                    for item in items:
                        _set_subcategory(item)
                    return items
        except Exception as e:
            print(f"[ERROR] split_expenses LLM failed, falling back to simple split: {type(e).__name__}: {e}", file=sys.stderr)

    return _simple_split_expenses(description, learned_categories)
