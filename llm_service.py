import google.generativeai as genai
import json
import re
from config import GEMINI_API_KEY, SEED_CATEGORIES

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


def extract_keywords(description):
    words = re.sub(r'[^\w\s]', '', description.lower()).split()
    return [w for w in words if len(w) >= 2]


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


def predict_expense(description, learned_categories=None):
    if not description or len(description) < 2:
        return None
    learned_cat = check_learned(description, learned_categories)
    if learned_cat:
        amount = extract_amount_fallback(description) or 0
        return {"category": learned_cat, "amount": amount}
    return extract_expense(description, learned_categories)
