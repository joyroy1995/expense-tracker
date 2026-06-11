import google.generativeai as genai
import json
import re
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Entertainment",
    "Health",
    "Education",
    "Rent",
    "Groceries",
    "Travel",
    "Personal Care",
    "Gifts",
    "Investment",
    "Savings",
    "Other",
]

CATEGORIES_STR = ", ".join(CATEGORIES)

SYSTEM_PROMPT = f"""You are an expense extraction assistant for a Bangladeshi user. The user will describe their expense in English, Bengali, or Banglish (Bengali written in English letters).

Your task:
1. Identify the expense category from: {CATEGORIES_STR}
2. Extract the amount in BDT from the text

Amount patterns to recognize:
- "30 taka", "50 tk", "100 taka"
- "৳100", "100৳"
- "100 টাকা", "৫০ টাকা"
- Bengali numerals: ১=1, ২=2, ৩=3, ৪=4, ৫=5, ৬=6, ৭=7, ৮=8, ৯=9, ০=0
- Just a number like "30" or "50" if context suggests it's an amount

Return ONLY a valid JSON object with this exact format:
{{"category": "CategoryName", "amount": 30}}

Do not add any explanation or extra text. Return only the JSON.

Examples:
- "badam kinlam 30 taka" -> {{"category": "Groceries", "amount": 30}}
- "rickshaw te office gelam 50 tk" -> {{"category": "Transport", "amount": 50}}
- "lunch at KFC 350" -> {{"category": "Food", "amount": 350}}
- "চা খেয়েছি ২০ টাকা" -> {{"category": "Food", "amount": 20}}
- "bus e bazar gelam 30" -> {{"category": "Transport", "amount": 30}}
- "movie ticket 500 taka" -> {{"category": "Entertainment", "amount": 500}}
- "pharmacy te oshudh 200 tk" -> {{"category": "Health", "amount": 200}}
- "electricity bill dibo 1500" -> {{"category": "Bills", "amount": 1500}}
- "daraz e jama kinlam 800 taka" -> {{"category": "Shopping", "amount": 800}}
- "bari bhara 15000" -> {{"category": "Rent", "amount": 15000}}
"""

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction=SYSTEM_PROMPT,
)


def bengali_to_english_num(text):
    bengali_digits = {"০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4", "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9"}
    for bn, en in bengali_digits.items():
        text = text.replace(bn, en)
    return text


def extract_amount_fallback(text):
    text = bengali_to_english_num(text)
    text = re.sub(r'(taka|tk|৳|টাকা)', '', text, flags=re.IGNORECASE).strip()
    numbers = re.findall(r'(\d+(?:\.\d+)?)', text)
    if numbers:
        return float(numbers[-1])
    return None


CATEGORY_KEYWORDS = {
    "Food": ["food", "lunch", "dinner", "breakfast", "kfc", "burger", "pizza", "cha", "tea", "coffee", "khabar", "kheyechi", "khawa", "restaurant", "cafe", "biryani", "khichuri", "vat", "ranna", "khailaam", "khelam", " hotel"],
    "Transport": ["rickshaw", "bus", "train", "launch", "metro", "uber", "pathao", "petrol", "fuel", "gas", "cng", "tempo", "plane", "flight", "fare", "car", "bike", "tuktuk", "taxi", "cab", "rail", "steamer", "ferry"],
    "Shopping": ["daraz", "shopping", "jama", "shirt", "pant", "shoe", "juta", "kapor", "cloth", "dress", "bag", "watch", "mobile", "phone", "gadget", "electronics"],
    "Bills": ["bill", "electricity", "electric", "gas bill", "water bill", "internet bill", "phone bill", "utility", "bills", "current bill"],
    "Entertainment": ["movie", "cinema", "film", "show", "concert", "game", "cricket", "football", "stadium", "netflix", "youtube", "spotify", "music", "song"],
    "Health": ["medicine", "oshudh", "pharmacy", "doctor", "hospital", "clinic", "checkup", "health", "daktar", "pathology", "drug", "tablet"],
    "Education": ["book", "boi", "course", "udemy", "class", "school", "college", "university", "tution", "tuition", "coaching", "admission", "exam", "test", "notebook", "khata", "pen", "kolom"],
    "Rent": ["rent", "bari bhara", "house rent", "flat", "lease"],
    "Groceries": ["bazar", "groceries", "vegetables", "sabji", "sabzi", "fish", "mach", "murgi", "chicken", "beef", "gosht", "mutton", "dim", "egg", "dudh", "milk", "dal", "chal", "rice", "tel", "oil", "moshla", "spice", "badam", "almond", "fruit", "fol"],
    "Travel": ["tour", "travel", "trip", "holiday", "vacation", "visit", "cox", "sylhet", "bandarban", "sajek", "kuakata", "saint martin", "resort"],
    "Personal Care": ["haircut", "salon", "parlor", "beauty", "nail", "spa", "massage", "grooming", "shaver", "trim"],
    "Gifts": ["gift", "birthday", "present", "anniversary", "wedding", "biye"],
    "Investment": ["investment", "share", "stock", "bonds", "bbs", "mutual fund", "dse", "cse"],
    "Savings": ["savings", "dps", "deposit", "sanchay", "bank", "account"],
}


def keyword_category(description):
    text = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return category
    return "Other"


def extract_expense(description):
    if not GEMINI_API_KEY:
        return {"category": keyword_category(description), "amount": extract_amount_fallback(description) or 0}

    try:
        response = model.generate_content(description)
        text = response.text.strip().strip("```").strip()

        if text.startswith("json"):
            text = text[4:].strip()

        result = json.loads(text)

        category = result.get("category", "Other")
        amount = float(result.get("amount", 0))

        if category not in CATEGORIES:
            for cat in CATEGORIES:
                if cat.lower() in category.lower():
                    category = cat
                    break
            else:
                category = "Other"

        if amount <= 0:
            fallback = extract_amount_fallback(description)
            if fallback:
                amount = fallback

        return {"category": category, "amount": amount}
    except Exception:
        amount = extract_amount_fallback(description)
        category = keyword_category(description)
        return {"category": category, "amount": amount or 0}


def predict_expense(description):
    if not description or len(description) < 2:
        return None
    return extract_expense(description)
