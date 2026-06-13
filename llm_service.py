from groq import Groq
import json
import re
import os
from datetime import date as _d, timedelta, date
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

_QUESTION_WORDS = {"what", "how", "why", "show", "tell", "list", "give", "which", "when", "where", "who", "did", "do", "does", "is", "are", "was", "were", "can", "could", "would", "will"}

def is_question(text):
    first = text.strip().lower().split(maxsplit=1)[0].rstrip("?,.")
    return first in _QUESTION_WORDS or text.strip().endswith("?")


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
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            temperature=0.1,
            max_tokens=100,
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

def _fmt_history(history):
    if not history:
        return ""
    lines = ["\n---\nConversation history:"]
    for h in history[-6:]:
        role = "User" if h["role"] == "user" else "Assistant"
        lines.append(f"{role}: {h['content']}")
    lines.append("---")
    return "\n".join(lines)


def _fmt_dates():
    today = date.today()
    ym = today.strftime("%Y-%m")
    prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    seven_days_ago = (today - timedelta(days=7)).isoformat()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    last_week_start = (today - timedelta(days=today.weekday() + 7)).isoformat()
    return today.isoformat(), ym, prev, today.strftime("%Y"), seven_days_ago, week_start, last_week_start

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
4. Use portable SQL with string-based date comparisons — avoid database-specific functions like `date()` or `strftime()`.
5. For date filtering:
   - Use LIKE with pattern: date LIKE '{current_month}%'
   - Use SUBSTR(date, 1, 4) for year extraction
   - Use SUBSTR(date, 1, 7) for year-month extraction
   - For date ranges use date >= 'YYYY-MM-DD' AND date <= 'YYYY-MM-DD'
   - Pre-computed relative dates — use as literal strings: today={today}, 7_days_ago={seven_days_ago}, week_start={week_start}, last_week_start={last_week_start}
6. Column names: id, date, description, amount, category, user_id, created_at
7. Use COALESCE for safe SUM/AVG aggregates.
8. Limit results to 50 rows max unless the user asks for a specific number.
9. Use single quotes for strings.
10. For the budgets table: amounts are monthly budgets, one row per category. Compare actual spending vs budget using LEFT JOIN and GROUP BY. Exception: for '__overall__' budget (total spending across ALL categories), use a scalar subquery instead of a JOIN on category.
11. For description search, use LIKE with %% wildcards: description LIKE '%%keyword%%'
12. When comparing periods, use SUBSTR(date, 1, 7) in GROUP BY or WHERE.
13. For frequency/count questions ("how many times", "most used category", "in terms of frequency", "how often"), use COUNT(*) instead of SUM(amount). If the user asks which category by frequency, use COUNT(*) as count and ORDER BY count DESC.

Examples:

Q: How much on Transport this month?
SQL: SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND category = 'Transport' AND date LIKE '{current_month}%'

Q: Show all my Dining Out expenses from last month
SQL: SELECT date, description, amount FROM expenses WHERE user_id = :uid AND category = 'Dining Out' AND date LIKE '{last_month}%' ORDER BY date

Q: What categories did I spend on this month?
SQL: SELECT category, COALESCE(SUM(amount), 0) as total, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category ORDER BY total DESC

Q: How much did I spend in the last 7 days?
SQL: SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date >= '{seven_days_ago}'

Q: List last 7 days expenses descending by date
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date >= '{seven_days_ago}' ORDER BY date DESC LIMIT 50

Q: What was my most expensive expense this month?
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' ORDER BY amount DESC LIMIT 1

Q: Average daily spending this month
SQL: SELECT COALESCE(AVG(daily.total), 0) as avg_daily FROM (SELECT SUM(amount) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY date) daily

Q: How many times did I eat out this month?
SQL: SELECT COUNT(*) as count FROM expenses WHERE user_id = :uid AND category = 'Dining Out' AND date LIKE '{current_month}%'

Q: Which category did I use the most this month by frequency?
SQL: SELECT category, COUNT(*) as count FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category ORDER BY count DESC LIMIT 1

Q: How does this month compare to last month?
SQL: SELECT SUBSTR(date, 1, 7) as month, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND (date LIKE '{current_month}%' OR date LIKE '{last_month}%') GROUP BY SUBSTR(date, 1, 7) ORDER BY month

Q: Which categories did I spend more than 1000 on this month?
SQL: SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%' GROUP BY category HAVING total > 1000 ORDER BY total DESC

Q: Show me all expenses where I used Uber or Pathao
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND (description LIKE '%uber%' OR description LIKE '%pathao%') ORDER BY date DESC LIMIT 50

Q: How much budget is left for Groceries this month?
SQL: SELECT b.category, b.amount as budget_amount, COALESCE(SUM(e.amount), 0) as spent, b.amount - COALESCE(SUM(e.amount), 0) as remaining FROM budgets b LEFT JOIN expenses e ON e.user_id = b.user_id AND e.category = b.category AND e.date LIKE '{current_month}%' WHERE b.user_id = :uid AND b.category = 'Groceries' GROUP BY b.id, b.category, b.amount

Q: Do I have budget left for Overall?
SQL: SELECT b.category, b.amount as budget_amount, (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%') as spent, b.amount - (SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date LIKE '{current_month}%') as remaining FROM budgets b WHERE b.user_id = :uid AND b.category = '__overall__'

Q: What are the top 5 categories I spend the most on this year?
SQL: SELECT category, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date LIKE '{current_year}%' GROUP BY category ORDER BY total DESC LIMIT 5

Q: Show all expenses from this week
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date >= '{week_start}' AND date <= '{today}' ORDER BY date

Q: How does this week compare to last week?
SQL: SELECT 'This week' as period, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = :uid AND date >= '{week_start}' AND date <= '{today}' UNION ALL SELECT 'Last week', COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = :uid AND date >= '{last_week_start}' AND date < '{week_start}'
Q: What was my largest expense last month?
SQL: SELECT date, description, amount, category FROM expenses WHERE user_id = :uid AND date LIKE '{last_month}%' ORDER BY amount DESC LIMIT 1

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


def generate_sql(question, schema, retries=1):
    if not _has_api_key():
        return None
    today, current_month, last_month, current_year, seven_days_ago, week_start, last_week_start = _fmt_dates()
    prompt = SQL_PROMPT.format(
        today=today, current_month=current_month, last_month=last_month,
        current_year=current_year, seven_days_ago=seven_days_ago,
        week_start=week_start, last_week_start=last_week_start,
        schema=schema, question=question,
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


CORRECT_SQL_PROMPT = """The SQL query below failed to execute. Fix it based on the error message.
Return ONLY the corrected SQL query — no explanation, no backticks.

Original SQL: {sql}
Error: {error}
Database schema:
{schema}
Original question: {question}

Rules:
- Return only the corrected SQL query
- Must be a SELECT statement
- Must include user_id = :uid in the WHERE clause
- Use SQLite-compatible syntax

Corrected SQL:"""


def correct_sql(sql, error, schema, question):
    """Attempt to fix a failed SQL query using the actual database error."""
    if not _has_api_key():
        return None
    prompt = CORRECT_SQL_PROMPT.format(sql=sql, error=error, schema=schema, question=question)
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
    """Format a category value for display, handling internal names like __overall__."""
    if not cat:
        return ""
    if cat == "__overall__":
        return "Overall"
    return cat


def format_answer(columns, data, question):
    """Generate natural language answer from query results without an LLM call."""
    if not data:
        return "No expenses found matching your question."

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

    # --- Budget remaining / status ---
    if remaining_col is not None and budget_col is not None:
        row = data[0]
        remaining = float(row.get(remaining_col, 0))
        budget = float(row.get(budget_col, 0))
        spent = float(row.get(amt_col, 0)) if amt_col else 0
        cat = _display_cat(row.get(cat_col, "")) if cat_col else ""
        prefix = f" for {cat}" if cat else ""
        if remaining > 0:
            return f"You have ৳{remaining:.2f} remaining{prefix} (spent ৳{spent:.2f} of ৳{budget:.2f} budget)."
        elif remaining == 0:
            return f"You have used your entire budget{prefix} (৳{budget:.2f})."
        else:
            return f"You have exceeded your budget{prefix} by ৳{abs(remaining):.2f} (spent ৳{spent:.2f} of ৳{budget:.2f})."

    # --- Single or multi-month comparison ---
    if month_col and amt_col and len(data) >= 2:
        rows_sorted = sorted(data, key=lambda r: r.get(month_col, ""))
        labels = []
        for r in rows_sorted:
            m = r.get(month_col, "")
            t = float(r.get(amt_col, 0))
            labels.append(f"{m} (৳{t:.2f})")
        return f"Monthly totals: {', '.join(labels)}."

    # --- Average value ---
    if avg_col:
        avg = float(data[0].get(avg_col, 0))
        cnt_val = float(data[0].get(cnt_col, 0)) if cnt_col else 0
        if cnt_val:
            return f"Average daily spending is ৳{avg:.2f} across {int(cnt_val)} day(s)."
        return f"Average is ৳{avg:.2f}."

    # --- Single aggregate (SUM, COUNT) ---
    if len(data) == 1 and not cat_col and not month_col:
        row = data[0]
        total = float(row.get(amt_col, 0)) if amt_col else None
        count = int(row.get(cnt_col, 0)) if cnt_col else None
        if total is not None and count is not None:
            return f"Your total is ৳{total:.2f} across {count} transaction(s)."
        if total is not None:
            return f"Your total is ৳{total:.2f}."
        if count is not None:
            return f"That's {count} transaction(s)."

    # --- Single result with description ---
    if len(data) == 1 and desc_col and amt_col:
        row = data[0]
        desc = row.get(desc_col, "")
        amt_val = float(row.get(amt_col, 0))
        date_val = row.get(date_col, "") if date_col else ""
        base = f"৳{amt_val:.2f} for \"{desc}\""
        if date_val:
            base += f" on {date_val}"
        return f"It was {base}."

    # --- Single result max/min ---
    if len(data) == 1 and (max_col or min_col):
        row = data[0]
        val = float(row.get(max_col or min_col, 0))
        desc = row.get(desc_col, "")
        cat = _display_cat(row.get(cat_col, ""))
        suffix = f" ({desc})" if desc else f" in {cat}" if cat else ""
        label = "Most" if max_col else "Least"
        return f"{label} expensive{suffix}: ৳{val:.2f}."

    # --- Category breakdown ---
    if cat_col and amt_col and len(data) > 1:
        total = sum(float(r.get(amt_col, 0)) for r in data)
        top = max(data, key=lambda r: float(r.get(amt_col, 0)))
        return f"Total: ৳{total:.2f} across {len(data)} categories. Most spent on {_display_cat(top[cat_col])} (৳{float(top[amt_col]):.2f})."

    # --- Category with count (frequency) ---
    if cat_col and cnt_col and len(data) == 1:
        row = data[0]
        cat = row.get(cat_col, "")
        cnt = int(row.get(cnt_col, 0))
        return f"Most used category: {_display_cat(cat)} ({cnt} transaction(s))."

    # --- General list ---
    total = sum(float(r.get(amt_col, 0)) for r in data) if amt_col else 0
    info = f" totaling ৳{total:.2f}" if amt_col else ""
    return f"Found {len(data)} result(s){info}."


# ── Expense Splitting ──────────────────────────────────────────

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


def extract_date_reference(text, now):
    """
    Extract date reference from user message (English / Banglish / Bengali).
    Returns (cleaned_text, date_str) where date_str is YYYY-MM-DD.
    """
    original = text.strip()
    if not original:
        return text, now.strftime('%Y-%m-%d')
    today = now.date() if hasattr(now, 'date') else now
    cleaned = original

    month_map = {
        'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
        'july':7,'august':8,'september':9,'october':10,'november':11,'december':12,
        'jan':1,'feb':2,'mar':3,'apr':4,'jun':6,'jul':7,'aug':8,
        'sep':9,'sept':9,'oct':10,'nov':11,'dec':12,
    }

    def _try_date(y, m, d):
        try: return date(int(y), int(m), int(d))
        except: return None

    def _sub_and_return(pattern, repl, date_val):
        nonlocal cleaned
        cleaned = re.sub(pattern, repl, cleaned, count=1, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned, date_val.strftime('%Y-%m-%d')

    # ── Explicit ISO: 2024-06-12 ──
    m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', cleaned)
    if m:
        d = _try_date(m.group(1), m.group(2), m.group(3))
        if d: return _sub_and_return(m.group(0), '', d)

    # ── Explicit DD/MM/YYYY or MM/DD/YYYY ──
    m = re.search(r'\b(\d{1,2})[/](\d{1,2})[/](\d{4})\b', cleaned)
    if m:
        for a,b in [(1,2),(2,1)]:
            d = _try_date(m.group(3), m.group(a), m.group(b))
            if d and d <= today: return _sub_and_return(m.group(0), '', d)

    # ── "June 12, 2024" or "12 June 2024" ──
    m = re.search(r'(?:on\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(' + '|'.join(month_map) + r')\s*,?\s*(\d{4})?', cleaned, re.IGNORECASE)
    if not m:
        m = re.search(r'(?:on\s+)?(' + '|'.join(month_map) + r')\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})?', cleaned, re.IGNORECASE)
        if m:
            day, month_name, year = m.group(2), m.group(1).lower(), m.group(3)
            month = month_map.get(month_name)
            if month:
                d = _try_date(year or today.year, month, day)
                if d: return _sub_and_return(m.group(0), '', d)
    else:
        day, month_name, year = m.group(1), m.group(2).lower(), m.group(3)
        month = month_map.get(month_name)
        if month:
            d = _try_date(year or today.year, month, day)
            if d: return _sub_and_return(m.group(0), '', d)

    # ── "the day before yesterday" / "পরশু" / "parshu" / "goto parshu" / "parshudin" ──
    if re.search(r'(?:the\s+)?day\s+before\s+yesterday|\bparshu\b|goto\s+parshu|গত পরশু|পরশুদিন|পরশু', cleaned, re.IGNORECASE):
        d = today - timedelta(days=2)
        return _sub_and_return(r'(?:the\s+)?day\s+before\s+yesterday|\bparshu\b|goto\s+parshu|গত পরশু|পরশুদিন|পরশু', '', d)

    # ── "the night before" / "previous day" / "previous night" ──
    if re.search(r'the\s+night\s+before|previous\s+day|previous\s+night', cleaned, re.IGNORECASE):
        d = today - timedelta(days=1)
        return _sub_and_return(r'the\s+night\s+before|previous\s+day|previous\s+night', '', d)

    # ── "yesterday" / "last day/date/night/evening/morning/afternoon" / "kalke" / "goto kalke" / "গতকাল" / "কাল" / "গত রাতে" / "goto rate" / "গত সকালে" / "goto shakale" / "গত দুপুরে" / "goto dupure" / "গত বিকেলে" / "goto bikele" ──
    if re.search(r'\byesterday\b|\blast\s+(?:day|date|night|evening|morning|afternoon)\b|\bkalke\b|\bgoto\s+kalke\b|গতকাল|কাল(?!\s*দুপুর)|গত\s+রাতে|goto\s+rate|গত\s+সকালে|goto\s+shakale|গত\s+দুপুরে|goto\s+dupure|গত\s+বিকেলে|goto\s+bikele', cleaned, re.IGNORECASE):
        d = today - timedelta(days=1)
        return _sub_and_return(r'\byesterday\b|\blast\s+(?:day|date|night|evening|morning|afternoon)\b|\bkalke\b|\bgoto\s+kalke\b|গতকাল|কাল(?!\s*দুপুর)|গত\s+রাতে|goto\s+rate|গত\s+সকালে|goto\s+shakale|গত\s+দুপুরে|goto\s+dupure|গত\s+বিকেলে|goto\s+bikele', '', d)

    # ── "today" / "this morning/afternoon/evening" / "tonight" / "earlier today" / "aaj" / "aj" / "ajke" / "আজ" / "আজকে" / "ai rate" / "ei rate" / "ai shakale" / "ei shakale" ──
    if re.search(r'\btoday\b|\btonight\b|this\s+(?:morning|afternoon|evening)|earlier\s+today|\baaj\b|\baj(?:ke)?\b|আজ(?:কে)?|ai\s+rate|ei\s+rate|ai\s+shakale|ei\s+shakale', cleaned, re.IGNORECASE):
        d = today
        return _sub_and_return(r'\btoday\b|\btonight\b|this\s+(?:morning|afternoon|evening)|earlier\s+today|\baaj\b|\baj(?:ke)?\b|আজ(?:কে)?|ai\s+rate|ei\s+rate|ai\s+shakale|ei\s+shakale', '', d)

    # ── "this week" / "this month" / "ei shoptaho/shopta" / "ei mashe/mash" / "এই সপ্তাহে" / "এই মাসে" ──
    m = re.search(r'this\s+week|ei\s+(?:shoptaho|shopta|shoptah)|এই\s+সপ্তাহে', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=today.weekday())  # go back to Monday
        return _sub_and_return(m.re.pattern, '', d)
    m = re.search(r'this\s+month|ei\s+(?:mashe|mash)|এই\s+মাসে', cleaned, re.IGNORECASE)
    if m:
        d = today.replace(day=1)
        return _sub_and_return(m.re.pattern, '', d)

    # ── "last week" / "goto shoptaho/shopta" / "গত সপ্তাহে" / "shesh shoptaho/shopta" / "শেষ সপ্তাহে" ──
    if re.search(r'last\s+week|goto\s+(?:shoptaho|shopta)|গত\s+সপ্তাহে|shesh\s+(?:shoptaho|shopta|shoptah)|শেষ\s+সপ্তাহে', cleaned, re.IGNORECASE):
        d = today - timedelta(days=7)
        return _sub_and_return(r'last\s+week|goto\s+(?:shoptaho|shopta)|গত\s+সপ্তাহে|shesh\s+(?:shoptaho|shopta|shoptah)|শেষ\s+সপ্তাহে', '', d)

    # ── "last month" / "goto mash" / "গত মাসে" / "shesh mashe/mash" / "শেষ মাসে" ──
    if re.search(r'last\s+month|goto\s+mash|গত\s+মাসে|shesh\s+(?:mashe|mash)|শেষ\s+মাসে', cleaned, re.IGNORECASE):
        d = today.replace(day=1) - timedelta(days=1)
        d = d.replace(day=min(today.day, 28))
        return _sub_and_return(r'last\s+month|goto\s+mash|গত\s+মাসে|shesh\s+(?:mashe|mash)|শেষ\s+মাসে', '', d)

    # ── "previous week" / "previous month" ──
    if re.search(r'previous\s+week', cleaned, re.IGNORECASE):
        d = today - timedelta(days=7)
        return _sub_and_return(r'previous\s+week', '', d)
    if re.search(r'previous\s+month', cleaned, re.IGNORECASE):
        d = today.replace(day=1) - timedelta(days=1)
        d = d.replace(day=min(today.day, 28))
        return _sub_and_return(r'previous\s+month', '', d)

    # ── "the week before last" / "the month before last" ──
    if re.search(r'(?:the\s+)?week\s+before\s+last', cleaned, re.IGNORECASE):
        d = today - timedelta(days=14)
        return _sub_and_return(r'(?:the\s+)?week\s+before\s+last', '', d)
    if re.search(r'(?:the\s+)?month\s+before\s+last', cleaned, re.IGNORECASE):
        d = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        return _sub_and_return(r'(?:the\s+)?month\s+before\s+last', '', d)

    # ── "a couple of days ago" / "a few days ago" / "koyekdin age/aage" / "কয়েকদিন আগে" ──
    m = re.search(r'(?:a\s+)?couple\s+of\s+days?\s+ago|koyek(?:din)?\s+(?:days?\s+ago|din\s+(?:age|aage)|দিন\s+আগে)|koyekdin\s+(?:age|aage)', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=2)
        return _sub_and_return(m.re.pattern, '', d)
    m = re.search(r'(?:a\s+)?few\s+days?\s+ago', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=3)
        return _sub_and_return(m.re.pattern, '', d)
    m = re.search(r'কয়েকদিন\s+আগে', cleaned)
    if m:
        d = today - timedelta(days=3)
        return _sub_and_return(m.re.pattern, '', d)

    # ── "N days ago" / "N din age/aage" / "N দিন আগে" ──
    m = re.search(r'(\d+)\s+(?:days?\s+ago|din\s+(?:age|aage)|দিন\s+আগে)', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=int(m.group(1)))
        return _sub_and_return(m.group(0), '', d)

    # ── "a week ago" / "shoptah age/aage" / "shopta age/aage" / "সপ্তাহ আগে" ──
    m = re.search(r'(?:a\s+)?week\s+ago|shoptah?(?:\s+age|\s+aage)|সপ্তাহ\s+আগে', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=7)
        return _sub_and_return(m.re.pattern, '', d)

    # ── "a month ago" / "mashe age/aage" / "mash age/aage" / "মাস আগে" ──
    m = re.search(r'(?:a\s+)?month\s+ago|mashe?\s+(?:age|aage)|মাস\s+আগে', cleaned, re.IGNORECASE)
    if m:
        d = (today.replace(day=1) - timedelta(days=1)).replace(day=min(today.day, 28))
        return _sub_and_return(m.re.pattern, '', d)

    # ── "N tarikhe" / "N tarikha" (Banglish date refs like "25 tarikhe") ──
    m = re.search(r'\b(\d{1,2})\s+tarikh[ea]\b', cleaned, re.IGNORECASE)
    if m:
        day_num = int(m.group(1))
        d = _try_date(today.year, today.month, day_num)
        if d and d <= today:
            return _sub_and_return(m.re.pattern, '', d)
        # Try previous month
        prev = today.replace(day=1) - timedelta(days=1)
        d = _try_date(prev.year, prev.month, day_num)
        if d and d <= today:
            return _sub_and_return(m.re.pattern, '', d)

    # ── "last monday", "last tuesday" etc. ──
    day_names = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    for i, day in enumerate(day_names):
        for prefix in [r'last\s+', r'this\s+', r'(?:on\s+)?']:
            p = re.compile(prefix + day, re.IGNORECASE)
            if p.search(cleaned):
                days_ago = (today.weekday() - i) % 7
                if prefix == r'last\s+' and days_ago == 0:
                    days_ago = 7
                d = today - timedelta(days=days_ago)
                return _sub_and_return(p.pattern, '', d)

    return original, today.strftime('%Y-%m-%d')


def _clean_split_desc(desc):
    """Strip trailing monetary amount/currency from a split item description."""
    d = desc.strip()
    d = re.sub(r'\b\d+(?:\.\d+)?\s*(?:taka|tk|৳|টাকা)\s*$', '', d, flags=re.IGNORECASE).strip()
    d = re.sub(r'\b(?:taka|tk|৳|টাকা)\s*\d+(?:\.\d+)?\s*$', '', d, flags=re.IGNORECASE).strip()
    d = re.sub(r'\s*\d+(?:\.\d+)?\s*$', '', d).strip()
    return d


def clean_date_refs(text):
    """Remove date/time references from a description string (for AI chat flow)."""
    d = text.strip()
    patterns = [
        (r'\b(?:yesterday|today|tomorrow|day\s+before\s+yesterday|the\s+night\s+before|previous\s+day|previous\s+night|previous\s+week|previous\s+month)\b', re.IGNORECASE),
        (r'(?:the\s+)?week\s+before\s+last|(?:the\s+)?month\s+before\s+last', re.IGNORECASE),
        (r'\btonight\b|this\s+(?:morning|afternoon|evening)|earlier\s+today', re.IGNORECASE),
        (r'\blast\s+(?:day|date|night|evening|morning|afternoon|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.IGNORECASE),
        (r'\bthis\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.IGNORECASE),
        (r'(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', re.IGNORECASE),
        (r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}(?:st|nd|rd|th)?\b', re.IGNORECASE),
        (r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b', re.IGNORECASE),
        (r'\b\d{4}-\d{1,2}-\d{1,2}\b', 0),
        (r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b', 0),
        (r'\b(?:a\s+)?couple\s+of\s+days?\s+ago\b|\b(?:a\s+)?few\s+days?\s+ago\b', re.IGNORECASE),
        (r'\b(?:a\s+)?week\s+ago\b|\b(?:a\s+)?month\s+ago\b', re.IGNORECASE),
        (r'\b\d+\s+(?:days?\s+ago|din\s+(?:age|aage)|দিন\s+আগে)\b', re.IGNORECASE),
        # Bangla / Banglish
        (r'\b(?:aaj|aj(?:ke)?)\b|আজ(?:কে)?', re.IGNORECASE),
        (r'\bkalke\b|\bparshu\b', re.IGNORECASE),
        (r'\bgoto\s+(?:parshu|kalke|rate|shakale|dupure|bikele)\b', re.IGNORECASE),
        (r'\b(?:ai|ei)\s+(?:rate|shakale)\b', re.IGNORECASE),
        (r'\b(?:ei|agami|shesh)\s+(?:shoptaho|shopta|shoptah|mashe|mash)\b', re.IGNORECASE),
        (r'গত\s+(?:রাতে|সকালে|দুপুরে|বিকেলে|পরশু|সপ্তাহে|মাসে)', 0),
        (r'শেষ\s+(?:সপ্তাহে|মাসে)', 0),
        (r'আগামী\s+(?:সপ্তাহে|মাসে)', 0),
        (r'এই\s+(?:সপ্তাহে|মাসে)', 0),
        (r'গতকাল|কাল(?!\s*দুপুর)|পরশুদিন|পরশু', 0),
        (r'কয়েকদিন\s+আগে|কয়েক\s+ঘন্টা\s+আগে', 0),
        (r'সপ্তাহ\s+আগে|মাস\s+আগে', 0),
        (r'\bkoyek(?:din)?\s+(?:days?\s+ago|din\s+(?:age|aage)|দিন\s+আগে)\b|\bkoyekdin\s+(?:age|aage)\b', re.IGNORECASE),
        (r'\bshoptah?(?:\s+age|\s+aage)\b|\bmashe?\s+(?:age|aage)\b', re.IGNORECASE),
        (r'\b\d{1,2}\s+tarikh[ea]\b', re.IGNORECASE),
    ]
    for pattern, flags in patterns:
        d = re.sub(pattern, '', d, flags=flags).strip()
    d = re.sub(r'\s+', ' ', d).strip()
    return d


def split_expenses(description):
    """Split a multi-item expense description into individual items."""
    if not _has_api_key():
        return None
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are an expense splitter. Return only a JSON array."},
                {"role": "user", "content": f"{SPLIT_PROMPT}\n\nInput: {description}\nOutput:"},
            ],
            temperature=0.1,
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
        # Leave single-item results as-is (caller decides if split is useful)
        return items
    except Exception:
        return None


# ── Budget Intent Detection ──────────────────────────────────────

def detect_budget_intent(text):
    """Detect if a user message is setting a budget (not an expense).
    Returns {"category": str, "amount": float} or None.
    Matches patterns like: "set food budget 5000", "add transport budget 3000",
    "set budget for food to 5000", "food budget 5000", "food er budget 5000",
    "khabarer budget 5000", "food a budget set koro 5000".
    """
    if not text:
        return None
    cleaned = text.strip().lower()
    # Remove common filler words
    cleaned = re.sub(r'\b(?:please|pls|koro|korun|koren|diben|diyo|set\s+koro|set\s+korun|set\s+koren|add\s+koro|add\s+korun|add\s+koren)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Pattern 0: Overall/total budget intent (check BEFORE category patterns)
    overall_patterns = [
        r'(?:set|add|new)?\s*(?:overall|total|monthly|general|maximum)\s+budget\s*(?:set)?\s*(?:koro|diben|diyo|set)?\s*(?:to|at|hole)?\s*(\d+(?:\.\d+)?)',
        r'(?:set|add|new)?\s*budget\s*(?:set)?\s*(?:for|of)?\s*(?:overall|total|monthly|general|maximum)\s*(?:koro|diben|diyo|set)?\s*(?:to|at|hole)?\s*(\d+(?:\.\d+)?)',
        r'(?:overall|total|monthly|maximum)\s+(?:spending\s+)?(?:limit|budget)\s*(?:hobe|hole|hocche)?\s*(\d+(?:\.\d+)?)',
        r'(?:set|add|new)?\s*(?:ekhon|amr|monthly|total)\s+budget\s*(?:set)?\s*(?:koro|diben|diyo)?\s*(\d+(?:\.\d+)?)',
    ]
    for pattern in overall_patterns:
        m = re.search(pattern, cleaned)
        if m:
            return {"category": "__overall__", "amount": float(m.group(1))}

    # Build category matching pattern — sort by length descending for greedy match
    cat_pattern = '|'.join(sorted(CATEGORIES, key=len, reverse=True))
    cat_pattern_lower = cat_pattern.lower()

    # Pattern 1: "set/add <category> budget <amount>" or "<category> budget <amount>"
    m = re.search(r'(?:set|add|new)?\s*(' + cat_pattern_lower + r')\s*(?:er|ar|or|theke|a)?\s*budget(?: set)?\s*(?:koro|diben|diyo|set)?\s*(?:to|hole)?\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        # Map back to canonical category name
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    # Pattern 2: "set budget for <category> to <amount>"
    m = re.search(r'set\s+budget\s+(?:for|of)\s+(' + cat_pattern_lower + r')\s+(?:to|at|hole)\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    # Pattern 3: "budget for <category> <amount>"
    m = re.search(r'budget\s+(?:for|of)\s+(' + cat_pattern_lower + r')\s*(?:is|hole)?\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    # Pattern 4: "<category> budget <amount>" (simplest form)
    m = re.search(r'(' + cat_pattern_lower + r')\s+budget\s*(?:hobe|hole|diben|diyo)?\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    return None


# ── Query Decomposition ──────────────────────────────────────

_COMPOUND_INDICATORS = [
    " and what ", " and how ", " and which ", " and who ",
    " and when ", " and where ", " and show ", " and tell ",
    " and list ", " and give ",
    " then ", " also ",
    "after that", "before that",
]

def _is_compound_question(question):
    q = question.lower().strip()
    return any(indicator in q for indicator in _COMPOUND_INDICATORS)


DECOMPOSE_PROMPT = """You are a query decomposition assistant. Given a compound user question about their expenses, break it into simpler sub-questions that can each be answered with a single SQL query.

Return ONLY a valid JSON object in this format:
{{"sub_questions": ["sub question 1", "sub question 2"]}}

If the question is simple (doesn't need decomposition), return: {{"simple": true}}

Guidelines:
- Each sub-question must be self-contained and answerable independently with one SQL query
- Max 3 sub-questions
- Include date context ("this month", "last month") in each sub-question if relevant
- Preserve any specific amounts, categories, or filters mentioned

Examples:

Q: How much did I spend on Food this month and what was my biggest Transport expense?
{{"sub_questions": ["How much on Food this month?", "What was my biggest Transport expense this month?"]}}

Q: Show me all expenses from my most expensive category this month
{{"sub_questions": ["What category did I spend the most on this month?", "Show all expenses in Food category this month"]}}

Q: What's my total spending this month and how many transactions did I make?
{{"sub_questions": ["What is my total spending this month?", "How many transactions did I make this month?"]}}

Q: How much on Transport this month?
{{"simple": true}}

Question: {question}
Return ONLY valid JSON:"""


def decompose_question(question, schema):
    """Break a compound question into simpler sub-questions. Returns None if simple."""
    if not _has_api_key():
        return None
    if not _is_compound_question(question):
        return None

    prompt = DECOMPOSE_PROMPT.format(question=question)
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a query decomposition assistant. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        text = response.choices[0].message.content.strip().strip("```").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        result = json.loads(text)
        if result.get("simple") or not result.get("sub_questions"):
            return None
        subs = result["sub_questions"]
        if len(subs) < 2:
            return None
        return subs[:3]
    except Exception:
        return None


COMPOSE_PROMPT = """You are a friendly Bangladeshi personal finance assistant. Today is {today}.

You answered several sub-questions for the user. Combine the results into a single natural answer.

Original question: {question}

Sub-results:
{sub_results}{history}

Rules:
- Provide a concise 1-3 sentence answer in English.
- Use ৳ symbol for BDT amounts.
- Round amounts to 2 decimal places.
- Do NOT mention sub-questions or the decomposition process.
- Be specific and helpful.

Answer:"""


def compose_answers(question, sub_results, history=None):
    """Combine results from multiple sub-questions into one answer."""
    if not _has_api_key():
        answers = [r.get("answer", "") for r in sub_results if r.get("answer")]
        return " ".join(answers) if answers else None

    today = _d.today().strftime("%B %d, %Y")
    results_str = "\n".join(
        f"Sub-answer {i+1}: {r.get('answer', '')}"
        for i, r in enumerate(sub_results)
    )
    hist_text = _fmt_history(history)

    prompt = COMPOSE_PROMPT.format(
        question=question, sub_results=results_str,
        today=today, history=hist_text,
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
        answers = [r.get("answer", "") for r in sub_results if r.get("answer")]
        return " ".join(answers) if answers else None


def transcribe_audio(audio_bytes, mime_type="audio/webm"):
    client = Groq()
    ext = mime_type.split("/")[-1] if "/" in mime_type else "webm"
    filename = f"audio.{ext}"
    transcript = client.audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=(filename, audio_bytes),
        response_format="text",
        language="en",
    )
    return transcript.strip()
