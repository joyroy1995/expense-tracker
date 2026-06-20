import re
from llm.categories import CATEGORIES


def detect_budget_intent(text):
    if not text:
        return None
    cleaned = text.strip().lower()
    cleaned = re.sub(r'\b(?:please|pls|koro|korun|koren|diben|diyo|set\s+koro|set\s+korun|set\s+koren|add\s+koro|add\s+korun|add\s+koren)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

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

    cat_pattern = '|'.join(sorted(CATEGORIES, key=len, reverse=True))
    cat_pattern_lower = cat_pattern.lower()

    m = re.search(r'(?:set|add|new)?\s*(' + cat_pattern_lower + r')\s*(?:er|ar|or|theke|a)?\s*budget(?: set)?\s*(?:koro|diben|diyo|set)?\s*(?:to|hole)?\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    m = re.search(r'set\s+budget\s+(?:for|of)\s+(' + cat_pattern_lower + r')\s+(?:to|at|hole)\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    m = re.search(r'budget\s+(?:for|of)\s+(' + cat_pattern_lower + r')\s*(?:is|hole)?\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    m = re.search(r'(' + cat_pattern_lower + r')\s+budget\s*(?:hobe|hole|diben|diyo)?\s*(\d+(?:\.\d+)?)', cleaned)
    if m:
        category = m.group(1).strip().title()
        for c in CATEGORIES:
            if c.lower() == category.lower():
                category = c
                break
        return {"category": category, "amount": float(m.group(2))}

    return None
