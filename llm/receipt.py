import json
import base64
import os
import re
import urllib.error
import urllib.request
import sys
from llm.categories import keyword_category, grocery_subcategory, extract_amount_fallback

RECEIPT_SCAN_PROMPT = """You are a receipt parser for a Bangladeshi expense tracker.
Given a receipt image, extract all line items.

For each item, return:
- description: the item name together with its quantity/units, e.g. "1 kg rice", "2 ta egg", "500 gm sugar"
- amount: ONLY the taka price for that line (number only, no currency symbol, no quantity like "2 x", "1 kg")
- subcategory: for grocery items only, one of Vegetables, Meat, Fish, Dairy & Eggs, Rice & Grains, Oils & Spices, Snacks & Drinks, General (e.g. murgi -> Meat, rui mach -> Fish, dim -> Dairy & Eggs, chal -> Rice & Grains, tel -> Oils & Spices). For non-grocery items set it to null.

If a store/merchant name or date is visible on the receipt, include them.
If the receipt text is in Bengali or Banglish, extract and return in that form.

Return ONLY a valid JSON object with this exact structure:
{"store": "store name or null", "date": "YYYY-MM-DD or null", "items": [{"description": "...", "amount": 123.45, "subcategory": "..."}]}

Do not add any explanation or extra text."""


def _normalize_amount(value):
    if isinstance(value, (int, float)):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    m = re.match(r"^(\d+)\s*[x*]\s*([\d.]+)$", text)
    if m:
        return float(m.group(1)) * float(m.group(2))
    text = re.sub(r"(taka|tk|৳|টাকা)", "", text, flags=re.IGNORECASE).strip()
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if nums:
        return float(nums[-1])
    return None


_GEMINI_MODELS = [
    "gemini-2.5-flash-latest",
    "gemini-3-flash-latest",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
]


def _scan_receipt_gemini_flash(image_bytes):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None, "GEMINI_API_KEY not configured"
    b64 = base64.b64encode(image_bytes).decode()

    payload = {
        "contents": [{
            "parts": [
                {"text": RECEIPT_SCAN_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ],
        }],
    }
    not_found_models = []
    for model in _GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip().strip("```").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
            parsed = json.loads(text)
            return parsed, None
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode(errors="replace")
            except Exception:
                pass
            if e.code == 404:
                not_found_models.append(model)
                print(f"[WARN] _scan_receipt_gemini_flash model {model} not found: {body or e.reason}", file=sys.stderr)
                continue
            error_msg = f"Gemini ({model}): HTTP {e.code} - {body or e.reason}"
            print(f"[ERROR] _scan_receipt_gemini_flash failed: {error_msg}", file=sys.stderr)
            return None, error_msg
        except json.JSONDecodeError as e:
            error_msg = f"Gemini ({model}): invalid JSON response - {e}"
            print(f"[ERROR] _scan_receipt_gemini_flash JSON decode error: {error_msg}", file=sys.stderr)
            return None, error_msg
        except Exception as e:
            error_msg = f"Gemini ({model}): {type(e).__name__} - {e}"
            print(f"[ERROR] _scan_receipt_gemini_flash failed: {error_msg}", file=sys.stderr)
            return None, error_msg
    if not_found_models:
        error_msg = f"Gemini: no available model (tried {', '.join(not_found_models)})"
    else:
        error_msg = "Gemini: no models to try"
    print(f"[ERROR] _scan_receipt_gemini_flash failed: {error_msg}", file=sys.stderr)
    return None, error_msg


def scan_receipt(image_bytes):
    def _categorize_items(items):
        for item in items:
            desc = item.get("description", "")
            category = keyword_category(desc)
            item["category"] = category
            if category == "Groceries":
                item["subcategory"] = grocery_subcategory(desc)
            else:
                item.pop("subcategory", None)
            amount = _normalize_amount(item.get("amount")) or extract_amount_fallback(desc) or 0
            item["amount"] = round(amount, 2)

    result, gemini_error = _scan_receipt_gemini_flash(image_bytes)
    if result is not None:
        if result.get("items"):
            _categorize_items(result["items"])
            return result
        return {"error": "Receipt detected but no line items found. Try a clearer photo."}
    print(f"[ERROR] scan_receipt failed: {gemini_error}", file=sys.stderr)
    error_msg = gemini_error or "No vision API available. Set GEMINI_API_KEY."
    return {"error": error_msg}
