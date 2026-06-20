import json
import base64
import os
import urllib.request
from llm.config import _get_client
from llm.categories import keyword_category, extract_amount_fallback

RECEIPT_SCAN_PROMPT = """You are a receipt parser for a Bangladeshi expense tracker.
Given a receipt image, extract all line items.

For each item, return:
- description: the item name (keep quantity like "1 kg", "2 ta", etc.)
- amount: the price in BDT (number only, no currency symbol)

If a store/merchant name or date is visible on the receipt, include them.
If the receipt text is in Bengali or Banglish, extract and return in that form.

Return ONLY a valid JSON object with this exact structure:
{"store": "store name or null", "date": "YYYY-MM-DD or null", "items": [{"description": "...", "amount": 123.45}]}

Do not add any explanation or extra text."""


def _scan_receipt_groq(image_bytes):
    client = _get_client()
    if not client:
        return None, "GROQ_API_KEY not configured"
    b64 = base64.b64encode(image_bytes).decode()
    models = ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.2-11b-vision-preview"]
    last_error = ""
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": RECEIPT_SCAN_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }],
                temperature=0.1,
                max_tokens=1000,
            )
            text = response.choices[0].message.content.strip().strip("```").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
            parsed = json.loads(text)
            return parsed, None
        except json.JSONDecodeError as e:
            last_error = f"Groq vision ({model}): invalid JSON response - {e}"
        except Exception as e:
            last_error = f"Groq vision ({model}): {type(e).__name__} - {e}"
        continue
    return None, last_error


def _scan_receipt_gemini(image_bytes):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None, "GEMINI_API_KEY not configured"
    b64 = base64.b64encode(image_bytes).decode()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": RECEIPT_SCAN_PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ],
        }],
    }
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
    except json.JSONDecodeError as e:
        return None, f"Gemini: invalid JSON response - {e}"
    except Exception as e:
        return None, f"Gemini: {type(e).__name__} - {e}"


def scan_receipt(image_bytes):
    def _categorize_items(items):
        for item in items:
            desc = item.get("description", "")
            item["category"] = keyword_category(desc)
            if not item.get("amount"):
                item["amount"] = extract_amount_fallback(desc) or 0

    result, error = _scan_receipt_groq(image_bytes)
    if result is not None:
        if result.get("items"):
            _categorize_items(result["items"])
            return result
        return {"error": "Receipt detected but no line items found. Try a clearer photo."}
    result, gemini_error = _scan_receipt_gemini(image_bytes)
    if result is not None:
        if result.get("items"):
            _categorize_items(result["items"])
            return result
        return {"error": "Receipt detected but no line items found. Try a clearer photo."}
    return {"error": error if error else gemini_error or "No vision API available. Set GROQ_API_KEY or GEMINI_API_KEY."}
