import re

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

CATEGORY_KEYWORDS = {
    "Food": ["food", "lunch", "dinner", "breakfast", "cha", "tea", "coffee", "khabar", "kheyechi", "khawa", "khichuri", "vat", "ranna", "khailaam", "khelam", " hotel", "bashi khabar", "bariye khabar"],
    "Transport": ["rickshaw", "bus", "train", "launch", "metro", "uber", "pathao", "petrol", "fuel", "gas", "cng", "tempo", "plane", "flight", "fare", "car", "bike", "tuktuk", "taxi", "cab", "rail", "steamer", "ferry"],
    "Shopping": ["daraz", "shopping", "jama", "shirt", "pant", "shoe", "juta", "kapor", "cloth", "dress", "bag", "watch", "mobile", "phone", "gadget", "electronics"],
    "Bills": ["bill", "electricity", "electric", "gas bill", "water bill", "internet bill", "phone bill", "utility", "bills", "current bill"],
    "Entertainment": ["movie", "cinema", "film", "show", "concert", "game", "cricket", "football", "stadium", "netflix", "youtube", "spotify", "music", "song"],
    "Health": ["medicine", "oshudh", "pharmacy", "doctor", "hospital", "clinic", "checkup", "health", "daktar", "pathology", "drug", "tablet"],
    "Education": ["book", "boi", "course", "udemy", "class", "school", "college", "university", "tution", "tuition", "coaching", "admission", "exam", "test", "notebook", "khata", "pen", "kolom"],
    "Rent": ["rent", "bari bhara", "house rent", "flat", "lease"],
    "Dining Out": ["restaurant", "hotel", "cafe", "kacchi", "khacci", "biryani", "biriani", "polao", "kabab", "fast food", "pizza", "burger", "kfc", "mcdonald", "takeout", "dine out", "baire kheye", "dawat", "party", "hotel e", "restaurant e", "khabar hotel", "kacchi vai", "khacci vai", "sultan's dine", "nanna", "restora", "buffet", "lunch out", "dinner out", "outing e kheye", "puri", "singara", "shamucha", "fuchka", "chaat", "jhalmuri", "morog kacchi", "morog khacci", "morog biryani", "chicken biryani", "chicken kacchi", "gorur kacchi", "gorur khacci", "beef biryani", "gorur biryani", "khashi kacchi", "khashi khacci", "mutton biryani", "mutton kacchi", "shahi biryani", "shahi kacchi", "shahi khacci", "dhakaiya kacchi", "dhakaiya khacci", "dhaka biryani", "dhakai biryani", "haji biryani", "haji kacchi", "haji khacci", "tehari", "tehari biryani", "achar kacchi", "achar khacci", "achar biryani", "hidly biryani", "hidli biryani", "hidly kacchi", "bhashani biryani", "bhashani kacchi", "sultan biryani", "sultan din biryani", "nawabi biryani", "hyderabadi biryani", "veg biryani", "vegetable biryani", "egg biryani", "kolkata biryani", "sindhi biryani", "chimney biryani", "handi biryani", "chinese biryani", "chinese", "chinese food", "chinese restaurant", "chiniya khabar", "chini restaurant", "noodles", "chowmein", "chow mein", "fried rice", "dim sum", "wonton", "spring roll", "manchurian", "kung pao", "szechuan", "hot pot", "thai", "thai food", "thai restaurant", "pad thai", "tom yum", "tom kha", "green curry", "red curry", "thai soup", "massaman", "pad krapow", "mishti", "misti", "roshmalai", "rasmalai", "roshogolla", "rasgulla", "chomchom", "chamcham", "kalojam", "jilapi", "jalebi", "shondesh", "sondesh", "patishapta", "payesh", "firni", "shemai", "halwa", "pitha", "bhapa pitha", "puli pitha", "pantua", "ledikeni", "malai chop", "mihidana", "sitabhog", "dudh malai", "bhapa sandesh", "chanar jilapi", "naru", "narkel naru", "moa", "gur", "patali", "misti doi", "lal doi", "mishti doi", "misty doi", "doi", "borhani", "lassi", "matha", "chaa", "cha er dokan", "coffee shop", "cafe coffee", "cold coffee", "pasta", "sandwich", "subway", "shawarma", "kebab", "kabab", "tandoori", "naan", "roti", "paratha", "porota"],
    "Fruits": ["fruit", "fol", "aam", "mango", "kola", "kol", "banana", "shufti", "apple", "kamola", "comla", "komola", "orange", "peyara", "guava", "kathal", "jackfruit", "anarosh", "pineapple", "angur", "grape", "dalim", "anar", "pomegranate", "tarmuj", "watermelon", "pepe", "papaya", "narikel", "coconut", "lichu", "lychee", "aata", "aamra", "custard apple", "boroi", "kul", "jujube", "jam", "kalo jam", "kalojam", "java plum", "bel", "wood apple", "jalpai", "olive", "lotkon", "tal", "palm", "dewa", "jambura", "pomelo", "dragon fruit", "dragon", "strawberry", "cherry", "peach", "nashpati", "pear", "alubokhara", "plum", "lebu", "lemon", "khajur", "date", "anjeer", "dumur", "fig", "kiwi", "bangi", "melon", "avocado", "passion fruit"],
    "Groceries": ["bazar", "groceries", "vegetables", "swapno", "shopno", "supershop", "supermarket", "sabji", "sabzi", "shosha", "gajor", "borboti", "aloo", "alu", "begun", "fulkopi", "badhakopi", "dherosh", "mula", "kumra", "lau", "korola", "potol", "jhinga", "chichinga", "shim", "kochu", "shak", "palong shak", "uchha", "kakrol", "tomato", "salad", "gach", "fish", "mach", "rui", "katla", "tilapia", "pangash", "koi", "chingri", "shutki", "machher dim", "murgi", "chicken", "beef", "goru", "gosht", "mutton", "khashi", "hash", "hansh", "dim", "egg", "dudh", "milk", "dal", "chal", "rice", "tel", "oil", "moshla", "spice", "badam", "almond", "peyaj", "roshun", "ada", "holud", "dhonia", "jira", "shorshe", "chira", "muri"],
    "Travel": ["tour", "travel", "trip", "holiday", "vacation", "visit", "cox", "sylhet", "bandarban", "sajek", "kuakata", "saint martin", "resort"],
    "Personal Care": ["haircut", "salon", "parlor", "beauty", "nail", "spa", "massage", "grooming", "shaver", "trim"],
    "Gifts": ["gift", "birthday", "present", "anniversary", "wedding", "biye"],
    "Investment": ["investment", "share", "stock", "bonds", "bbs", "mutual fund", "dse", "cse"],
    "Savings": ["savings", "dps", "deposit", "sanchay", "bank", "account"],
}

GROCERY_SUBCATEGORIES = [
    "Vegetables",
    "Meat",
    "Fish",
    "Dairy & Eggs",
    "Rice & Grains",
    "Oils & Spices",
    "Snacks & Drinks",
    "General",
]

GROCERY_SUBCATEGORIES_STR = ", ".join(GROCERY_SUBCATEGORIES)

SUBCATEGORY_KEYWORDS = {
    "Vegetables": [
        "shosha", "gajor", "borboti", "aloo", "alu", "begun", "fulkopi", "badhakopi",
        "dherosh", "mula", "kumra", "lau", "korola", "potol", "jhinga", "chichinga",
        "shim", "kochu", "shak", "palong shak", "uchha", "kakrol", "tomato", "salad",
        "vegetable", "sabji", "sabzi", "sobji", "শাক", "সবজি", "শসা", "গাজর", "আলু",
        "বেগুন", "ফুলকপি", "ধে", "ধেড়োশ", "মুলা", "কুমড়া", "লাউ", "করলা", "পটল",
        "টমেটো", "কচু",
    ],
    "Meat": [
        "murgi", "murghi", "chicken", "beef", "goru", "gosht", "goshti", "mutton",
        "khashi", "hash", "hansh", "meat", "mangsho", "broiler", "cow", "গরুর মাংস",
        "মুরগি", "খাসি", "হাঁস", "মাংস",
    ],
    "Fish": [
        "fish", "mach", "rui", "katla", "tilapia", "pangash", "pangas", "koi",
        "chingri", "shutki", "machher dim", "ilish", "hilsha", "pabda", "shing",
        "magur", "tengra", "মাছ", "মাছের ডিম", "রুই", "কাতলা", "চিংড়ি", "শুঁটকি", "ইলিশ",
    ],
    "Dairy & Eggs": [
        "dim", "egg", "dudh", "milk", "doi", "yogurt", "ghee", "paneer", "misti doi",
        "ডিম", "দুধ", "দই", "ঘি",
    ],
    "Rice & Grains": [
        "chal", "rice", "chira", "muri", "dal", "lentil", "ata", "aata", "maida",
        "suji", "noodles", "ডাল", "চাল", "চিড়া", "মুড়ি", "আটা",
    ],
    "Oils & Spices": [
        "tel", "oil", "moshla", "moshala", "spice", "holud", "dhonia", "jira", "jira",
        "shorshe", "ada", "roshun", "peyaj", "peyaj", "onion", "garlic", "ginger",
        "chili", "mirchi", "morich", "lobongo", "darchini", "তেল", "মসলা", "পেঁয়াজ",
        "রসুন", "আদা", "হলুদ", "ধনিয়া", "জিরা", "সরিষা", "মরিচ",
    ],
    "Snacks & Drinks": [
        "biscuit", "bisquit", "chocolate", "choklet", "chips", "chanachur", "chanar chur",
        "cola", "coke", "pepsi", "7up", "lemonade", "juice", "cold drink", "cola",
        "kola drink", "drink", "snack", "chotpoti", "badam", "almond", "kachari",
        "বিস্কুট", "চানাচুর", "চকলেট", "জুস",
    ],
}

_SUBCATEGORY_GENERAL = "General"

_EXCLUDE_KEYWORDS = {"taka", "tk", "টাকা", "৳", "bdt"}


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


def keyword_category(description):
    text = description.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return category
    return "Other"


def grocery_subcategory(description):
    text = description.lower()
    for subcat, keywords in SUBCATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return subcat
    return _SUBCATEGORY_GENERAL
