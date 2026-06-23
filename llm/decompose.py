import json
from datetime import date as _d
from llm.config import _get_client, _has_api_key
from llm.qa import _fmt_history

_QUESTION_WORDS = {"what", "how", "why", "show", "tell", "list", "give", "which", "when", "where", "who", "did", "do", "does", "is", "are", "was", "were", "can", "could", "would", "will"}

_COMPOUND_INDICATORS = [
    " and what ", " and how ", " and which ", " and who ",
    " and when ", " and where ", " and show ", " and tell ",
    " and list ", " and give ",
    " then ", " also ",
    "after that", "before that",
]


def is_question(text):
    stripped = text.strip()
    if not stripped:
        return False
    first = stripped.lower().split(maxsplit=1)[0].rstrip("?,.")
    return first in _QUESTION_WORDS or stripped.endswith("?")


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

{history}
Question: {question}
Return ONLY valid JSON:"""


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


def decompose_question(question, schema, history=None):
    if not _has_api_key():
        return None
    if not _is_compound_question(question):
        return None

    hist_text = _fmt_history(history, max_entries=3)
    prompt = DECOMPOSE_PROMPT.format(question=question, history=hist_text)
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


def _extract_text(a):
    return a.get("text", str(a)) if isinstance(a, dict) else str(a)


def compose_answers(question, sub_results, history=None):
    if not _has_api_key():
        answers = [_extract_text(r.get("answer", "")) for r in sub_results if r.get("answer")]
        return " ".join(answers) if answers else None

    today = _d.today().strftime("%B %d, %Y")
    results_str = "\n".join(
        f"Sub-answer {i+1}: {_extract_text(r.get('answer', ''))}"
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
        answers = [_extract_text(r.get("answer", "")) for r in sub_results if r.get("answer")]
        return " ".join(answers) if answers else None
