import os
import re
import sys
import time as _time
from datetime import datetime
from config import TIMEZONE
import database as db
from llm import generate_sql, correct_sql, answer_from_results, format_answer, decompose_question, compose_answers, extract_date_reference
from services.sql_service import SqlService
from services.pattern_engine import PatternEngine


COMPLEX_KEYWORDS = [
    "compare", "comparison", "difference", "vs ", "versus",
    "trend", "pattern",
    "unusual", "abnormal", "unexpected", "strange",
    "why", "because", "reason",
    "recommend", "suggestion", "tip", "advice",
    "insight", "summarize", "summary", "overview",
    "improve", "save", "reduce", "cut",
    "increased", "decreased", "rose", "fell",
    "budget", "budget left", "budget remaining", "exceed", "overspend",
    "remaining", "left",
    "percentage", "percent", "ratio",
    "change", "growth", "decline",
    "average", "avg", "mean",
    "highest", "lowest", "most", "least", "top", "bottom",
    "do i spend more", "do i spend less",
    "on track", "how am i doing",
    "monthly comparison", "month over month",
]

_schema_cache = None
_schema_cache_time = 0
_pattern_engine = PatternEngine()

_TRACE_ENABLED = os.environ.get("QA_TRACE", "0") == "1"


def _log_trace(question, trace):
    if not _TRACE_ENABLED:
        return
    stages = [f"{k}={v}ms" for k, v in trace.items() if isinstance(v, (int, float))]
    print(f"[TRACE] {trace.get('source', 'cache')} | {' | '.join(stages)} | q={question[:60]}", file=sys.stderr)


class QaService:

    @staticmethod
    def needs_llm_answer(question):
        q = question.lower()
        return any(kw in q for kw in COMPLEX_KEYWORDS)

    @staticmethod
    def normalize_question(text):
        if re.search(r'\bhow\s+does\s+this\s+month\s+compare\b', text, re.IGNORECASE):
            return text
        text = re.sub(
            r'\bcompare\s+(?:to|with)\s+last\s+month\b',
            'How does this month compare to last month',
            text, flags=re.IGNORECASE,
        )
        text = re.sub(
            r'\bcompare\s+(?:to|with)\s+previous\s+month\b',
            'How does this month compare to last month',
            text, flags=re.IGNORECASE,
        )
        text = re.sub(
            r'\bthis\s+month\s+vs\.?\s+last\s+month\b',
            'How does this month compare to last month',
            text, flags=re.IGNORECASE,
        )
        text = re.sub(
            r'\bmonth\s+over\s+month\b',
            'How does this month compare to last month',
            text, flags=re.IGNORECASE,
        )

        text = re.sub(r'\bajke\b', 'today', text, flags=re.IGNORECASE)
        text = re.sub(r'\bg[eo]t[oa]k[oa]l\b', 'yesterday', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(?:agami\s+)?kal\b', 'tomorrow', text, flags=re.IGNORECASE)
        text = re.sub(r'\bei\s+m[ae]s{1,2}h\b', 'this month', text, flags=re.IGNORECASE)
        text = re.sub(r'\bg[eo]t[oa]l\s+m[ae]s{1,2}h\b', 'last month', text, flags=re.IGNORECASE)
        text = re.sub(r'\bag[ei]\s+m[ae]s{1,2}h\b', 'next month', text, flags=re.IGNORECASE)
        text = re.sub(r'\bei\s+saptah\b', 'this week', text, flags=re.IGNORECASE)
        text = re.sub(r'\bg[eo]t[oa]l\s+saptah\b', 'last week', text, flags=re.IGNORECASE)
        text = re.sub(r'\bei\s+m[ea]s{1,2}h[eo]r\b', 'this year', text, flags=re.IGNORECASE)

        text = re.sub(r'\bk[ou]t[oau]\b', 'how much', text, flags=re.IGNORECASE)
        text = re.sub(r'\bd[eé]kh[auo]+n?\b', 'show', text, flags=re.IGNORECASE)
        text = re.sub(r'\bk[oay]t[aio]\b', 'how many', text, flags=re.IGNORECASE)
        text = re.sub(r'\bkoyta\b', 'how many', text, flags=re.IGNORECASE)
        text = re.sub(r'\bkh[oau]r[oau]c[ho]\b', 'spending', text, flags=re.IGNORECASE)
        text = re.sub(r'\bp[ou]r[ou]n[oau]\b', 'total', text, flags=re.IGNORECASE)
        text = re.sub(r'\bpouro\b', 'total', text, flags=re.IGNORECASE)

        return text

    @staticmethod
    def get_schema_cached():
        global _schema_cache, _schema_cache_time
        now = _time.time()
        if _schema_cache and now - _schema_cache_time < 300:
            return _schema_cache
        _schema_cache = db.get_schema()
        _schema_cache_time = now
        return _schema_cache

    @staticmethod
    def run_qa_pipeline(question, question_with_context, schema, history, uid, force_programmatic=False):
        trace = {}
        t0 = _time.time()

        t = _time.time()
        cached = db.get_cached_response(question_with_context, schema)
        trace["response_cache"] = round((_time.time() - t) * 1000, 1)
        if cached:
            return {
                "answer": cached["answer"],
                "sql": cached["sql"],
                "data": cached["response_data"].get("rows", []),
                "columns": cached["response_data"].get("columns", []),
                "from_cache": True,
                "trace": trace,
            }

        sql = None
        from_pattern = False

        t = _time.time()
        pattern_result = _pattern_engine.match(question)
        trace["pattern_engine"] = round((_time.time() - t) * 1000, 1)
        if pattern_result:
            sql = pattern_result[0]
            from_pattern = True
            trace["source"] = "pattern"
        else:
            t = _time.time()
            try:
                sql = generate_sql(question_with_context, schema, history=history)
            except Exception as e:
                return {"error": f"LLM query failed: {str(e)}", "trace": trace}
            trace["llm_gen"] = round((_time.time() - t) * 1000, 1)
            if not sql:
                return {"error": "Could not generate SQL query. Check API key.", "trace": trace}
            trace["source"] = "llm"

        t = _time.time()
        if not SqlService.validate_sql(sql):
            return {"error": "Generated query is not a valid SELECT statement", "sql": sql, "trace": trace}

        sql = SqlService.ensure_user_filter(sql)
        sql = SqlService.apply_all_fixes(sql, question)
        trace["sql_fixes"] = round((_time.time() - t) * 1000, 1)

        t = _time.time()
        try:
            conn = db.get_connection()
            result = conn.execute(db.text(sql), {"uid": uid})
            columns = list(result.keys()) if result.returns_rows else []
            rows = result.fetchmany(50)
            rows_data = [dict(r._mapping) for r in rows]
        except Exception as e:
            corrected = correct_sql(sql, str(e), schema, question_with_context, history=history)
            if corrected and SqlService.validate_sql(corrected):
                corrected = SqlService.ensure_user_filter(corrected)
                corrected = SqlService.apply_all_fixes(corrected, question)
                try:
                    conn2 = db.get_connection()
                    result = conn2.execute(db.text(corrected), {"uid": uid})
                    columns = list(result.keys()) if result.returns_rows else []
                    rows = result.fetchmany(50)
                    rows_data = [dict(r._mapping) for r in rows]
                    sql = corrected
                except Exception:
                    return {"error": f"Query execution failed: {str(e)}", "sql": sql, "corrected_sql": corrected, "trace": trace}
            else:
                return {"error": f"Query execution failed: {str(e)}", "sql": sql, "trace": trace}
        trace["exec"] = round((_time.time() - t) * 1000, 1)

        t = _time.time()
        validation_issues = SqlService.validate_results(question, columns, rows_data)
        if validation_issues:
            trace["validation_issues"] = validation_issues
        trace["validate"] = round((_time.time() - t) * 1000, 1)

        t = _time.time()
        if from_pattern:
            answer = format_answer(columns, rows_data, question)
        elif QaService.needs_llm_answer(question) and not force_programmatic:
            answer = answer_from_results(question, sql, rows_data[:20], history=history)
            if not answer:
                answer = format_answer(columns, rows_data, question)
        else:
            answer = format_answer(columns, rows_data, question)
        trace["answer"] = round((_time.time() - t) * 1000, 1)

        t = _time.time()
        db.cache_response(question_with_context, sql, {"rows": rows_data[:50], "columns": columns}, answer, schema)
        trace["cache_write"] = round((_time.time() - t) * 1000, 1)

        trace["total"] = round((_time.time() - t0) * 1000, 1)
        _log_trace(question, trace)

        confidence = 0.8
        if from_pattern:
            confidence = 1.0
        elif "corrected" in trace.get("source", ""):
            confidence = 0.7
        if not rows_data:
            confidence = min(confidence, 0.4)
        validation_issues = trace.get("validation_issues", [])
        if validation_issues:
            confidence = min(confidence, 0.5)

        result = {
            "answer": answer, "sql": sql,
            "data": rows_data[:50], "columns": columns,
            "trace": trace, "confidence": confidence,
        }
        return result

    @staticmethod
    def answer_question(question, history, uid):
        question = QaService.normalize_question(question)
        schema = QaService.get_schema_cached()
        current_date = datetime.now(TIMEZONE).strftime("%B %d, %Y")
        cleaned_for_date, expense_date = extract_date_reference(question, datetime.now(TIMEZONE))
        date_context = f"Today is {current_date}."
        if expense_date:
            date_context += f" The user is referring to date {expense_date}."
        question_with_context = f"{date_context}\n\nQuestion: {cleaned_for_date}"

        sub_questions = decompose_question(question_with_context, schema, history=history)

        if sub_questions:
            sub_results = []
            for sq in sub_questions:
                sq_with_context = f"{date_context}\n\nQuestion: {sq}"
                result = QaService.run_qa_pipeline(sq, sq_with_context, schema, history, uid, force_programmatic=True)
                if "error" not in result:
                    result["sub_question"] = sq
                    sub_results.append(result)

            if not sub_results:
                return None

            answer = compose_answers(question, sub_results, history=history)
            if not answer:
                answer = " ".join(r["answer"] for r in sub_results if r.get("answer"))

            all_sql = "; ".join(r["sql"] for r in sub_results if r.get("sql"))
            all_data = []
            seen = set()
            for r in sub_results:
                for row in r.get("data", []):
                    k = tuple(sorted(row.items()))
                    if k not in seen:
                        seen.add(k)
                        all_data.append(row)

            trace = {}
            if sub_results:
                for r in sub_results:
                    if "trace" in r:
                        for k, v in r["trace"].items():
                            trace.setdefault(k, 0)
                            if isinstance(v, (int, float)):
                                trace[k] = round(trace[k] + v, 1)
            _log_trace(question, trace)

            return {
                "answer": answer,
                "sql": all_sql,
                "data": all_data[:50],
                "columns": sub_results[0].get("columns", []) if sub_results else [],
                "decomposed": True,
                "trace": trace,
            }

        result = QaService.run_qa_pipeline(question, question_with_context, schema, history, uid)
        if "error" in result:
            return result
        return {"type": "question", **result}
