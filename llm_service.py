from groq import Groq
import json
import re
import os
from config import SEED_CATEGORIES

CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Entertainment",
    "Health",
    "Education",
    "Rent",
    "Dining Out",
    "Fruits",
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

Vegetable names in Banglish (all map to Groceries): shosha (cucumber), gajor (carrot), borboti (beans), aloo (potato), begun (eggplant), fulkopi (cauliflower), badhakopi (cabbage), dherosh (okra), mula (radish), kumra (pumpkin), lau (bottle gourd), korola (bitter gourd), potol (pointed gourd), shim (broad beans), kochu (taro), shak/palong shak (spinach/leafy greens), chira (flattened rice), muri (puffed rice), etc.

Meat/fish names in Banglish (all map to Groceries): murgi/murghi (chicken), gorur mangsho/beef (beef), khashi mangsho/mutton (goat meat), hash/hansh (duck), rui mach (rohu fish), katla mach, chingri (prawn/shrimp), shutki (dried fish), tilapia, pangash, koi mach, machher dim (fish roe), dim (egg).

Fruits is for any fruit purchases in any context. If a fruit name is found, always use Fruits category, even if the text also mentions bazar/groceries. Fruit names followed by "juice" (e.g. "mango juice", "aamer juice") belong to Dining Out.

Dining Out is for meals eaten outside the home at restaurants, hotels, cafes, fast food joints, street food, or any food/drink purchased and consumed away from home. Any fruit juice belongs to Dining Out. Food is for general food items/snacks at home.

Examples:
- "shosha ar gajor kinlam 40 taka" -> {{"category": "Groceries", "amount": 40}}
- "borboti ar aloo 30 tk" -> {{"category": "Groceries", "amount": 30}}
- "murgi kinlam 220 taka" -> {{"category": "Groceries", "amount": 220}}
- "gorur mangsho 600 tk" -> {{"category": "Groceries", "amount": 600}}
- "rui mach 350 taka" -> {{"category": "Groceries", "amount": 350}}
- "chingri kinlam 500 tk" -> {{"category": "Groceries", "amount": 500}}
- "badam kinlam 30 taka" -> {{"category": "Groceries", "amount": 30}}
- "bazar theke fulkopi ar begun anlam 120" -> {{"category": "Groceries", "amount": 120}}
- "aam kinlam 200 taka" -> {{"category": "Fruits", "amount": 200}}
- "kola ar peyara 80 tk" -> {{"category": "Fruits", "amount": 80}}
- "bazar theke angur ar apple anlam 300" -> {{"category": "Fruits", "amount": 300}}
- "lichu kinlam 150" -> {{"category": "Fruits", "amount": 150}}
- "tarmuj kinechi 120" -> {{"category": "Fruits", "amount": 120}}
- "swapno theke fol kinlam 500" -> {{"category": "Fruits", "amount": 500}}
- "mango juice 80 tk" -> {{"category": "Dining Out", "amount": 80}}
- "aamer juice khelam 60" -> {{"category": "Dining Out", "amount": 60}}
- "restaurant e biryani khelam 350" -> {{"category": "Dining Out", "amount": 350}}
- "kacchi khailam 450 taka" -> {{"category": "Dining Out", "amount": 450}}
- "khacci biryani 400 tk" -> {{"category": "Dining Out", "amount": 400}}
- "morog biryani 250" -> {{"category": "Dining Out", "amount": 250}}
- "hotel e lunch 250" -> {{"category": "Dining Out", "amount": 250}}
- "fuchka khelam 50 taka" -> {{"category": "Dining Out", "amount": 50}}
- "pizza hut theke pizza 1200" -> {{"category": "Dining Out", "amount": 1200}}
- "chinese fried rice 300" -> {{"category": "Dining Out", "amount": 300}}
- "chowmein khelam 150" -> {{"category": "Dining Out", "amount": 150}}
- "pad thai 200 tk" -> {{"category": "Dining Out", "amount": 200}}
- "swapno theke bazar korlam 1500" -> {{"category": "Groceries", "amount": 1500}}
- "shopno te kinlam 800" -> {{"category": "Groceries", "amount": 800}}
- "mishti khelam 200 taka" -> {{"category": "Dining Out", "amount": 200}}
- "roshmalai kinlam 150" -> {{"category": "Dining Out", "amount": 150}}
- "ice cream khailam 100" -> {{"category": "Dining Out", "amount": 100}}
- "jilapi diye cha 60" -> {{"category": "Dining Out", "amount": 60}}
- "rickshaw te office gelam 50 tk" -> {{"category": "Transport", "amount": 50}}
- "lunch at home 350" -> {{"category": "Food", "amount": 350}}
- "চা খেয়েছি ২০ টাকা" -> {{"category": "Food", "amount": 20}}
- "bus e bazar gelam 30" -> {{"category": "Transport", "amount": 30}}
- "movie ticket 500 taka" -> {{"category": "Entertainment", "amount": 500}}
- "pharmacy te oshudh 200 tk" -> {{"category": "Health", "amount": 200}}
- "electricity bill dibo 1500" -> {{"category": "Bills", "amount": 1500}}
- "daraz e jama kinlam 800 taka" -> {{"category": "Shopping", "amount": 800}}
- "bari bhara 15000" -> {{"category": "Rent", "amount": 15000}}
"""

def _get_client():
    key = os.environ.get("GROQ_API_KEY", "")
    return Groq(api_key=key) if key else None


def _has_api_key():
    return bool(os.environ.get("GROQ_API_KEY", ""))


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
    "Food": ["food", "lunch", "dinner", "breakfast", "cha", "tea", "coffee", "khabar", "kheyechi", "khawa", "khichuri", "vat", "ranna", "khailaam", "khelam", " hotel", "bashi khabar", "bariye khabar"],
    "Transport": ["rickshaw", "bus", "train", "launch", "metro", "uber", "pathao", "petrol", "fuel", "gas", "cng", "tempo", "plane", "flight", "fare", "car", "bike", "tuktuk", "taxi", "cab", "rail", "steamer", "ferry"],
    "Shopping": ["daraz", "shopping", "jama", "shirt", "pant", "shoe", "juta", "kapor", "cloth", "dress", "bag", "watch", "mobile", "phone", "gadget", "electronics"],
    "Bills": ["bill", "electricity", "electric", "gas bill", "water bill", "internet bill", "phone bill", "utility", "bills", "current bill"],
    "Entertainment": ["movie", "cinema", "film", "show", "concert", "game", "cricket", "football", "stadium", "netflix", "youtube", "spotify", "music", "song"],
    "Health": ["medicine", "oshudh", "pharmacy", "doctor", "hospital", "clinic", "checkup", "health", "daktar", "pathology", "drug", "tablet"],
    "Education": ["book", "boi", "course", "udemy", "class", "school", "college", "university", "tution", "tuition", "coaching", "admission", "exam", "test", "notebook", "khata", "pen", "kolom"],
    "Rent": ["rent", "bari bhara", "house rent", "flat", "lease"],
    "Dining Out": ["restaurant", "hotel", "cafe", "kacchi", "khacci", "biryani", "biriani", "polao", "kabab", "fast food", "pizza", "burger", "kfc", "mcdonald", "takeout", "dine out", "baire kheye", "dawat", "party", "hotel e", "restaurant e", "khabar hotel", "kacchi vai", "khacci vai", "sultan's dine", "nanna", "restora", "buffet", "lunch out", "dinner out", "outing e kheye", "puri", "singara", "shamucha", "fuchka", "chaat", "jhalmuri", "morog kacchi", "morog khacci", "morog biryani", "chicken biryani", "chicken kacchi", "gorur kacchi", "gorur khacci", "beef biryani", "gorur biryani", "khashi kacchi", "khashi khacci", "mutton biryani", "mutton kacchi", "shahi biryani", "shahi kacchi", "shahi khacci", "dhakaiya kacchi", "dhakaiya khacci", "dhaka biryani", "dhakai biryani", "haji biryani", "haji kacchi", "haji khacci", "tehari", "tehari biryani", "achar kacchi", "achar khacci", "achar biryani", "hidly biryani", "hidli biryani", "hidly kacchi", "bhashani biryani", "bhashani kacchi", "sultan biryani", "sultan din biryani", "nawabi biryani", "hyderabadi biryani", "veg biryani", "vegetable biryani", "egg biryani", "kolkata biryani", "sindhi biryani", "chimney biryani", "handi biryani", "chinese biryani", "chinese", "chinese food", "chinese restaurant", "chiniya khabar", "chini restaurant", "noodles", "chowmein", "chow mein", "fried rice", "dim sum", "wonton", "spring roll", "manchurian", "kung pao", "szechuan", "hot pot", "thai", "thai food", "thai restaurant", "pad thai", "tom yum", "tom kha", "green curry", "red curry", "thai soup", "massaman", "pad krapow", "mishti", "misti", "roshmalai", "rasmalai", "roshogolla", "rasgulla", "chomchom", "chamcham", "kalojam", "jilapi", "jalebi", "shondesh", "sondesh", "patishapta", "payesh", "firni", "shemai", "halwa", "pitha", "bhapa pitha", "puli pitha", "pantua", "ledikeni", "malai chop", "mihidana", "sitabhog", "dudh malai", "bhapa sandesh", "chanar jilapi", "naru", "narkel naru", "moa", "gur", "patali", "misti doi", "lal doi", "borhani", "dessert", "ice cream", "chocolate", "cake", "pastry", "donut", "doughnut", "brownie", "muffin", "cookie", "pudding", "custard", "milkshake", "juice", "juice"],
    "Fruits": ["fruit", "fol", "aam", "mango", "kola", "kol", "banana", "shufti", "apple", "kamola", "comla", "komola", "orange", "peyara", "guava", "kathal", "jackfruit", "anarosh", "pineapple", "angur", "grape", "dalim", "anar", "pomegranate", "tarmuj", "watermelon", "pepe", "papaya", "narikel", "coconut", "lichu", "lychee", "aata", "aamra", "custard apple", "boroi", "kul", "jujube", "jam", "kalo jam", "kalojam", "java plum", "bel", "wood apple", "jalpai", "olive", "lotkon", "tal", "palm", "dewa", "jambura", "pomelo", "dragon fruit", "dragon", "strawberry", "cherry", "peach", "nashpati", "pear", "alubokhara", "plum", "lebu", "lemon", "khajur", "date", "anjeer", "dumur", "fig", "kiwi", "bangi", "melon", "avocado", "passion fruit"],
    "Groceries": ["bazar", "groceries", "vegetables", "swapno", "shopno", "supershop", "supermarket", "sabji", "sabzi", "shosha", "gajor", "borboti", "aloo", "alu", "begun", "fulkopi", "badhakopi", "dherosh", "mula", "kumra", "lau", "korola", "potol", "jhinga", "chichinga", "shim", "kochu", "shak", "palong shak", "uchha", "kakrol", "tomato", "salad", "gach", "fish", "mach", "rui", "katla", "tilapia", "pangash", "koi", "chingri", "shutki", "machher dim", "murgi", "chicken", "beef", "goru", "gosht", "mutton", "khashi", "hash", "hansh", "dim", "egg", "dudh", "milk", "dal", "chal", "rice", "tel", "oil", "moshla", "spice", "badam", "almond", "peyaj", "roshun", "ada", "holud", "dhonia", "jira", "shorshe", "chira", "muri"],
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


_EXCLUDE_KEYWORDS = {"taka", "tk", "টাকা", "৳", "bdt"}

def extract_keywords(description):
    words = re.sub(r'[^\w\s]', '', description.lower()).split()
    return [w for w in words if len(w) >= 2
            and not w.isdigit()
            and w not in _EXCLUDE_KEYWORDS]


def check_learned(description, learned_dict=None):
    keywords = extract_keywords(description)
    combined = dict(SEED_CATEGORIES)
    if learned_dict:
        combined.update(learned_dict)
    for kw in keywords:
        if kw in combined:
            return combined[kw]
    return None


def extract_expense(description, learned_categories=None):
    learned_cat = check_learned(description, learned_categories)
    if learned_cat:
        amount = extract_amount_fallback(description) or 0
        return {"category": learned_cat, "amount": amount}

    if not _has_api_key():
        return {"category": keyword_category(description), "amount": extract_amount_fallback(description) or 0}

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            temperature=0.1,
        )
        text = response.choices[0].message.content.strip().strip("```").strip()

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


def predict_expense(description, learned_categories=None):
    if not description or len(description) < 2:
        return None
    learned_cat = check_learned(description, learned_categories)
    if learned_cat:
        amount = extract_amount_fallback(description) or 0
        return {"category": learned_cat, "amount": amount}
    return extract_expense(description, learned_categories)


# ── NL Q&A ──────────────────────────────────────────────────

SQL_PROMPT = """You are a SQL query generator for a personal expense tracker. Given a user's natural language question, generate a SQL query to answer it.

Database schema:
{schema}

Rules:
1. Return ONLY the SQL query — no explanation, no markdown formatting, no backticks.
2. Use ONLY SELECT queries.
3. Always include "user_id = :uid" in the WHERE clause.
4. Use SQLite-compatible syntax (works with both SQLite and PostgreSQL).
5. For date filtering use LIKE: date LIKE '2026-06%'
6. For extracting year/month use SUBSTR(date, 1, 4) for year, SUBSTR(date, 1, 7) for year-month.
7. Do NOT use date(), strftime(), EXTRACT(), or other date functions.
8. Column names: id, date, description, amount, category, user_id, created_at
9. Use COALESCE for safe SUM.
10. Limit results to 50 rows max.
11. Use single quotes for strings.

Examples:
Question: How much did I spend on chira this month?
SQL: SELECT SUM(amount) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND description LIKE '%chira%' AND date LIKE '2026-06%'

Question: What was my biggest expense last week?
SQL: SELECT description, amount, date, category FROM expenses WHERE user_id = :uid AND date >= '2026-06-07' AND date <= '2026-06-13' ORDER BY amount DESC LIMIT 1

Question: Show me all Dining Out expenses from June
SQL: SELECT date, description, amount FROM expenses WHERE user_id = :uid AND category = 'Dining Out' AND date LIKE '2026-06%' ORDER BY date

Question: What's my total spending on Transport this year?
SQL: SELECT SUM(amount) as total FROM expenses WHERE user_id = :uid AND category = 'Transport' AND date LIKE '2026-%'

Question: How many expenses did I have last month?
SQL: SELECT COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '2026-05%'

Question: What categories did I spend money on in June?
SQL: SELECT category, SUM(amount) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '2026-06%' GROUP BY category ORDER BY total DESC

Question: {question}

SQL:"""


ANSWER_PROMPT = """You are a friendly Bangladeshi personal finance assistant. Given a user's question, the SQL query used, and the results, provide a clear and concise natural language answer.

Question: {question}
SQL: {sql}
Results: {results}

Rules:
- Provide a concise 1-3 sentence answer in English.
- If results are empty, say so politely.
- Use ৳ symbol for BDT amounts.
- Round amounts to 2 decimal places.
- Be specific and helpful.
- Do NOT mention SQL or technical details unless the user specifically asks.

Answer:"""


def generate_sql(question, schema):
    if not _has_api_key():
        return None
    prompt = SQL_PROMPT.format(schema=schema, question=question)
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a SQL query generator. Return only the SQL query."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        sql = response.choices[0].message.content.strip().strip("```").strip()
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()
        if sql.lower().startswith("select") or sql.upper().startswith("SELECT"):
            return sql
        return None
    except Exception:
        return None


def answer_from_results(question, sql, results):
    if not _has_api_key():
        return None
    results_str = json.dumps(results, indent=2, ensure_ascii=False)
    prompt = ANSWER_PROMPT.format(question=question, sql=sql, results=results_str)
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a friendly Bangladeshi personal finance assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None
