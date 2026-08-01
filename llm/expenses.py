import json
import re
import calendar
from datetime import date, timedelta
from config import SEED_CATEGORIES
from llm.config import _get_client, _has_api_key, FAST_MODEL
from llm.categories import CATEGORIES, CATEGORIES_STR, GROCERY_SUBCATEGORIES, GROCERY_SUBCATEGORIES_STR, keyword_category, grocery_subcategory, extract_amount_fallback, bengali_to_english_num, _EXCLUDE_KEYWORDS

SYSTEM_PROMPT = f"""You are an expense extraction assistant for a Bangladeshi user. The user will describe their expense in English, Bengali, or Banglish (Bengali written in English letters).

Your task:
1. Identify the expense category from: {CATEGORIES_STR}
2. If the category is "Groceries", also identify the subcategory from: {GROCERY_SUBCATEGORIES_STR}
3. Extract the amount in BDT from the text

Amount patterns to recognize:
- "30 taka", "50 tk", "100 taka"
- "৳100", "100৳"
- "100 টাকা", "৫০ টাকা"
- Bengali numerals: ১=1, ২=2, ৩=3, ৪=4, ৫=5, ৬=6, ৭=7, ৮=8, ৯=9, ০=0
- Just a number like "30" or "50" if context suggests it's an amount

Grocery subcategory rules:
- Vegetables: shosha, gajor, aloo, begun, fulkopi, shak, tomato, and other sabji/sabzi
- Meat: murgi/murghi (chicken), gorur mangsho/beef, khashi/mutton, hash (duck)
- Fish: rui, katla, tilapia, pangash, chingri, shutki, machher dim, any mach
- Dairy & Eggs: dim (egg), dudh (milk), doi (yogurt), ghee
- Rice & Grains: chal (rice), chira, muri, dal
- Oils & Spices: tel (oil), moshla, peyaj (onion), ada (ginger), holud, dhonia, jira
- Snacks & Drinks: biscuit, chanachur, badam, juice, cold drink
- General: anything else grocery-related (e.g. "bazar korlam" without a specific item)

Return ONLY a valid JSON object with this exact format:
{{"category": "CategoryName", "subcategory": "SubcategoryName", "amount": 30}}

For non-Groceries categories, set "subcategory" to null.

Do not add any explanation or extra text. Return only the JSON.

Vegetable names in Banglish (all map to Groceries): shosha (cucumber), gajor (carrot), borboti (beans), aloo (potato), begun (eggplant), fulkopi (cauliflower), badhakopi (cabbage), dherosh (okra), mula (radish), kumra (pumpkin), lau (bottle gourd), korola (bitter gourd), potol (pointed gourd), shim (broad beans), kochu (taro), shak/palong shak (spinach/leafy greens), chira (flattened rice), muri (puffed rice), etc.

Meat/fish names in Banglish (all map to Groceries): murgi/murghi (chicken), gorur mangsho/beef (beef), khashi mangsho/mutton (goat meat), hash/hansh (duck), rui mach (rohu fish), katla mach, chingri (prawn/shrimp), shutki (dried fish), tilapia, pangash, koi mach, machher dim (fish roe), dim (egg).

Fruits is for any fruit purchases in any context. If a fruit name is found, always use Fruits category, even if the text also mentions bazar/groceries. Fruit names followed by "juice" (e.g. "mango juice", "aamer juice") belong to Dining Out.

Dining Out is for meals eaten outside the home at restaurants, hotels, cafes, fast food joints, street food, or any food/drink purchased and consumed away from home. Any fruit juice belongs to Dining Out. Food is for general food items/snacks at home.

Examples:
- "shosha ar gajor kinlam 40 taka" -> {{"category": "Groceries", "subcategory": "Vegetables", "amount": 40}}
- "borboti ar aloo 30 tk" -> {{"category": "Groceries", "subcategory": "Vegetables", "amount": 30}}
- "murgi kinlam 220 taka" -> {{"category": "Groceries", "subcategory": "Meat", "amount": 220}}
- "gorur mangsho 600 tk" -> {{"category": "Groceries", "subcategory": "Meat", "amount": 600}}
- "rui mach 350 taka" -> {{"category": "Groceries", "subcategory": "Fish", "amount": 350}}
- "chingri kinlam 500 tk" -> {{"category": "Groceries", "subcategory": "Fish", "amount": 500}}
- "badam kinlam 30 taka" -> {{"category": "Groceries", "subcategory": "Snacks & Drinks", "amount": 30}}
- "bazar theke fulkopi ar begun anlam 120" -> {{"category": "Groceries", "subcategory": "Vegetables", "amount": 120}}
- "dim ar dudh kinlam 100" -> {{"category": "Groceries", "subcategory": "Dairy & Eggs", "amount": 100}}
- "5 kg chal 350" -> {{"category": "Groceries", "subcategory": "Rice & Grains", "amount": 350}}
- "aam kinlam 200 taka" -> {{"category": "Fruits", "subcategory": null, "amount": 200}}
- "kola ar peyara 80 tk" -> {{"category": "Fruits", "subcategory": null, "amount": 80}}
- "bazar theke angur ar apple anlam 300" -> {{"category": "Fruits", "subcategory": null, "amount": 300}}
- "lichu kinlam 150" -> {{"category": "Fruits", "subcategory": null, "amount": 150}}
- "tarmuj kinechi 120" -> {{"category": "Fruits", "subcategory": null, "amount": 120}}
- "swapno theke fol kinlam 500" -> {{"category": "Fruits", "subcategory": null, "amount": 500}}
- "mango juice 80 tk" -> {{"category": "Dining Out", "subcategory": null, "amount": 80}}
- "aamer juice khelam 60" -> {{"category": "Dining Out", "subcategory": null, "amount": 60}}
- "restaurant e biryani khelam 350" -> {{"category": "Dining Out", "subcategory": null, "amount": 350}}
- "kacchi khailam 450 taka" -> {{"category": "Dining Out", "subcategory": null, "amount": 450}}
- "khacci biryani 400 tk" -> {{"category": "Dining Out", "subcategory": null, "amount": 400}}
- "morog biryani 250" -> {{"category": "Dining Out", "subcategory": null, "amount": 250}}
- "hotel e lunch 250" -> {{"category": "Dining Out", "subcategory": null, "amount": 250}}
- "fuchka khelam 50 taka" -> {{"category": "Dining Out", "subcategory": null, "amount": 50}}
- "pizza hut theke pizza 1200" -> {{"category": "Dining Out", "subcategory": null, "amount": 1200}}
- "chinese fried rice 300" -> {{"category": "Dining Out", "subcategory": null, "amount": 300}}
- "chowmein khelam 150" -> {{"category": "Dining Out", "subcategory": null, "amount": 150}}
- "pad thai 200 tk" -> {{"category": "Dining Out", "subcategory": null, "amount": 200}}
- "swapno theke bazar korlam 1500" -> {{"category": "Groceries", "subcategory": "General", "amount": 1500}}
- "shopno te kinlam 800" -> {{"category": "Groceries", "subcategory": "General", "amount": 800}}
- "mishti khelam 200 taka" -> {{"category": "Dining Out", "subcategory": null, "amount": 200}}
- "roshmalai kinlam 150" -> {{"category": "Dining Out", "subcategory": null, "amount": 150}}
- "ice cream khailam 100" -> {{"category": "Dining Out", "subcategory": null, "amount": 100}}
- "jilapi diye cha 60" -> {{"category": "Dining Out", "subcategory": null, "amount": 60}}
- "rickshaw te office gelam 50 tk" -> {{"category": "Transport", "subcategory": null, "amount": 50}}
- "lunch at home 350" -> {{"category": "Food", "subcategory": null, "amount": 350}}
- "চা খেয়েছি ২০ টাকা" -> {{"category": "Food", "subcategory": null, "amount": 20}}
- "bus e bazar gelam 30" -> {{"category": "Transport", "subcategory": null, "amount": 30}}
- "movie ticket 500 taka" -> {{"category": "Entertainment", "subcategory": null, "amount": 500}}
- "pharmacy te oshudh 200 tk" -> {{"category": "Health", "subcategory": null, "amount": 200}}
- "electricity bill dibo 1500" -> {{"category": "Bills", "subcategory": null, "amount": 1500}}
- "daraz e jama kinlam 800 taka" -> {{"category": "Shopping", "subcategory": null, "amount": 800}}
- "bari bhara 15000" -> {{"category": "Rent", "subcategory": null, "amount": 15000}}
"""


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


def _with_subcategory(category, subcategory, description):
    if category == "Groceries":
        if subcategory not in GROCERY_SUBCATEGORIES:
            subcategory = grocery_subcategory(description)
    else:
        subcategory = None
    return subcategory


def extract_expense(description, learned_categories=None):
    learned_cat = check_learned(description, learned_categories)
    if learned_cat:
        amount = extract_amount_fallback(description) or 0
        return {
            "category": learned_cat,
            "subcategory": _with_subcategory(learned_cat, None, description),
            "amount": amount,
        }

    if not _has_api_key():
        category = keyword_category(description)
        return {
            "category": category,
            "subcategory": _with_subcategory(category, None, description),
            "amount": extract_amount_fallback(description) or 0,
        }

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
            temperature=0.1,
            max_completion_tokens=120,
        )
        text = response.choices[0].message.content.strip().strip("```").strip()

        if text.startswith("json"):
            text = text[4:].strip()

        result = json.loads(text)

        category = result.get("category", "Other")
        amount = float(result.get("amount", 0))
        subcategory = result.get("subcategory") or None

        if category not in CATEGORIES:
            for cat in CATEGORIES:
                if cat.lower() in category.lower():
                    category = cat
                    break
            else:
                category = "Other"

        subcategory = _with_subcategory(category, subcategory, description)

        if amount <= 0:
            fallback = extract_amount_fallback(description)
            if fallback:
                amount = fallback

        return {"category": category, "subcategory": subcategory, "amount": amount}
    except Exception:
        amount = extract_amount_fallback(description)
        category = keyword_category(description)
        return {
            "category": category,
            "subcategory": _with_subcategory(category, None, description),
            "amount": amount or 0,
        }


def predict_expense(description, learned_categories=None):
    if not description or len(description) < 2:
        return None
    learned_cat = check_learned(description, learned_categories)
    if learned_cat:
        amount = extract_amount_fallback(description) or 0
        return {
            "category": learned_cat,
            "subcategory": _with_subcategory(learned_cat, None, description),
            "amount": amount,
        }
    return extract_expense(description, learned_categories)


def extract_date_reference(text, now):
    original = text.strip()
    if not original:
        return text, now.strftime('%Y-%m-%d')
    today = now.date() if hasattr(now, 'date') else now
    cleaned = original

    if re.search(
        r'\b(?:compare|comparison|vs\.?|versus|difference\s+between|month\s+over\s+month)\b',
        cleaned, re.IGNORECASE,
    ):
        return original, ""

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

    m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', cleaned)
    if m:
        d = _try_date(m.group(1), m.group(2), m.group(3))
        if d: return _sub_and_return(m.group(0), '', d)

    m = re.search(r'\b(\d{1,2})[/](\d{1,2})[/](\d{4})\b', cleaned)
    if m:
        for a,b in [(1,2),(2,1)]:
            d = _try_date(m.group(3), m.group(a), m.group(b))
            if d and d <= today: return _sub_and_return(m.group(0), '', d)

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

    if re.search(r'(?:the\s+)?day\s+before\s+yesterday|\bparshu\b|goto\s+parshu|গত পরশু|পরশুদিন|পরশু', cleaned, re.IGNORECASE):
        d = today - timedelta(days=2)
        return _sub_and_return(r'(?:the\s+)?day\s+before\s+yesterday|\bparshu\b|goto\s+parshu|গত পরশু|পরশুদিন|পরশু', '', d)

    if re.search(r'the\s+night\s+before|previous\s+day|previous\s+night', cleaned, re.IGNORECASE):
        d = today - timedelta(days=1)
        return _sub_and_return(r'the\s+night\s+before|previous\s+day|previous\s+night', '', d)

    if re.search(r'\byesterday\b|\blast\s+(?:day|date|night|evening|morning|afternoon)\b|\bkalke\b|\bgoto\s+kalke\b|গতকাল|কাল(?!\s*দুপুর)|গত\s+রাতে|goto\s+rate|গত\s+সকালে|goto\s+shakale|গত\s+দুপুরে|goto\s+dupure|গত\s+বিকেলে|goto\s+bikele', cleaned, re.IGNORECASE):
        d = today - timedelta(days=1)
        return _sub_and_return(r'\byesterday\b|\blast\s+(?:day|date|night|evening|morning|afternoon)\b|\bkalke\b|\bgoto\s+kalke\b|গতকাল|কাল(?!\s*দুপুর)|গত\s+রাতে|goto\s+rate|গত\s+সকালে|goto\s+shakale|গত\s+দুপুরে|goto\s+dupure|গত\s+বিকেলে|goto\s+bikele', '', d)

    if re.search(r'\btoday\b|\btonight\b|this\s+(?:morning|afternoon|evening)|earlier\s+today|\baaj\b|\baj(?:ke)?\b|আজ(?:কে)?|ai\s+rate|ei\s+rate|ai\s+shakale|ei\s+shakale', cleaned, re.IGNORECASE):
        d = today
        return _sub_and_return(r'\btoday\b|\btonight\b|this\s+(?:morning|afternoon|evening)|earlier\s+today|\baaj\b|\baj(?:ke)?\b|আজ(?:কে)?|ai\s+rate|ei\s+rate|ai\s+shakale|ei\s+shakale', '', d)

    m = re.search(r'this\s+week|ei\s+(?:shoptaho|shopta|shoptah)|এই\s+সপ্তাহে', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=today.weekday())
        return _sub_and_return(m.re.pattern, '', d)
    m = re.search(r'this\s+month|ei\s+(?:mashe|mash)|এই\s+মাসে', cleaned, re.IGNORECASE)
    if m:
        d = today.replace(day=1)
        return _sub_and_return(m.re.pattern, '', d)

    if re.search(r'last\s+week|goto\s+(?:shoptaho|shopta)|গত\s+সপ্তাহে|shesh\s+(?:shoptaho|shopta|shoptah)|শেষ\s+সপ্তাহে', cleaned, re.IGNORECASE):
        d = today - timedelta(days=7)
        return _sub_and_return(r'last\s+week|goto\s+(?:shoptaho|shopta)|গত\s+সপ্তাহে|shesh\s+(?:shoptaho|shopta|shoptah)|শেষ\s+সপ্তাহে', '', d)

    if re.search(r'last\s+month|goto\s+mash|গত\s+মাসে|shesh\s+(?:mashe|mash)|শেষ\s+মাসে', cleaned, re.IGNORECASE):
        d = today.replace(day=1) - timedelta(days=1)
        d = d.replace(day=min(today.day, 28))
        return _sub_and_return(r'last\s+month|goto\s+mash|গত\s+মাসে|shesh\s+(?:mashe|mash)|শেষ\s+মাসে', '', d)

    if re.search(r'previous\s+week', cleaned, re.IGNORECASE):
        d = today - timedelta(days=7)
        return _sub_and_return(r'previous\s+week', '', d)
    if re.search(r'previous\s+month', cleaned, re.IGNORECASE):
        d = today.replace(day=1) - timedelta(days=1)
        d = d.replace(day=min(today.day, 28))
        return _sub_and_return(r'previous\s+month', '', d)

    if re.search(r'(?:the\s+)?week\s+before\s+last', cleaned, re.IGNORECASE):
        d = today - timedelta(days=14)
        return _sub_and_return(r'(?:the\s+)?week\s+before\s+last', '', d)
    if re.search(r'(?:the\s+)?month\s+before\s+last', cleaned, re.IGNORECASE):
        d = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        return _sub_and_return(r'(?:the\s+)?month\s+before\s+last', '', d)

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

    m = re.search(r'(\d+)\s+(?:days?\s+ago|din\s+(?:age|aage)|দিন\s+আগে)', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=int(m.group(1)))
        return _sub_and_return(m.group(0), '', d)

    m = re.search(r'(?:a\s+)?week\s+ago|shoptah?(?:\s+age|\s+aage)|সপ্তাহ\s+আগে', cleaned, re.IGNORECASE)
    if m:
        d = today - timedelta(days=7)
        return _sub_and_return(m.re.pattern, '', d)

    m = re.search(r'(?:a\s+)?month\s+ago|mashe?\s+(?:age|aage)|মাস\s+আগে', cleaned, re.IGNORECASE)
    if m:
        d = (today.replace(day=1) - timedelta(days=1)).replace(day=min(today.day, 28))
        return _sub_and_return(m.re.pattern, '', d)

    m = re.search(r'\b(\d{1,2})\s+tarikh[ea]\b', cleaned, re.IGNORECASE)
    if m:
        day_num = int(m.group(1))
        d = _try_date(today.year, today.month, day_num)
        if d and d <= today:
            return _sub_and_return(m.re.pattern, '', d)
        prev = today.replace(day=1) - timedelta(days=1)
        d = _try_date(prev.year, prev.month, day_num)
        if d and d <= today:
            return _sub_and_return(m.re.pattern, '', d)

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


def clean_date_refs(text):
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
