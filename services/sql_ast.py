import sqlparse
from sqlparse.sql import Where, Comparison
from sqlparse.tokens import Keyword


def _token_positions(stmt):
    pos = 0
    for token in stmt.tokens:
        val = str(token)
        start = pos
        end = pos + len(val)
        yield token, start, end
        pos = end


def _find_where_positions(sql):
    parsed = sqlparse.parse(sql)
    if not parsed:
        return None
    stmt = parsed[0]
    for token, start, end in _token_positions(stmt):
        if isinstance(token, Where):
            return start, end
        if hasattr(token, 'tokens'):
            sub_start = start
            for sub in token.tokens:
                sv = str(sub)
                if isinstance(sub, Where):
                    return sub_start, sub_start + len(sv)
                sub_start += len(sv)
    return None


def add_condition(sql, condition):
    wr = _find_where_positions(sql)
    if wr is None:
        pos = _find_insert_pos(sql)
        return sql[:pos] + f" WHERE {condition} " + sql[pos:]
    start, end = wr
    clause = sql[start:end]
    stripped = clause.strip()
    after = sql[end:]
    if stripped.upper().startswith("WHERE") and len(stripped) > 5:
        rest = stripped[5:].strip()
        if rest:
            return sql[:end].rstrip() + f" AND {condition} " + after.lstrip()
    return sql[:end].rstrip() + f" {condition} " + after.lstrip()


def remove_condition(sql, column_pattern):
    wr = _find_where_positions(sql)
    if wr is None:
        return sql
    start, end = wr
    clause = sql[start:end]
    clause_lower = clause.lower()
    col_lower = column_pattern.lower()

    if col_lower not in clause_lower:
        return sql

    conds = _split_ands(clause)
    remaining = [c for c in conds if col_lower not in c.lower().strip()]
    if len(remaining) == len(conds):
        return sql

    if not remaining:
        before = sql[:start].rstrip()
        after_part = sql[end:].lstrip()
        if before.upper().endswith("WHERE"):
            before = before[:-5].rstrip()
        elif before.upper().endswith("AND"):
            before = before[:-3].rstrip()
        return before + " " + after_part

    new_where = "WHERE " + " AND ".join(remaining)
    return sql[:start] + new_where + sql[end:].lstrip()


def replace_condition(sql, old_pattern, new_condition):
    wr = _find_where_positions(sql)
    if wr is None:
        return sql
    start, end = wr
    clause = sql[start:end]

    conds = _split_ands(clause)
    replaced = False
    new_conds = []
    for c in conds:
        if old_pattern.lower() in c.lower():
            new_conds.append(new_condition)
            replaced = True
        else:
            new_conds.append(c)
    if not replaced:
        return sql
    new_where = "WHERE " + " AND ".join(new_conds)
    return sql[:start] + new_where + sql[end:].lstrip()


def has_condition(sql, column_pattern):
    wr = _find_where_positions(sql)
    if wr is None:
        return False
    clause = sql[wr[0]:wr[1]]
    return column_pattern.lower() in clause.lower()


def _split_ands(clause):
    text = clause.strip()
    for kw in ["WHERE", "where"]:
        if text.startswith(kw):
            text = text[len(kw):].strip()
            break
    depth = 0
    parts = []
    current = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
        elif depth == 0 and i + 5 <= len(text) and text[i:i+5].upper() == ' AND ':
            parts.append(current.strip())
            current = ""
            i += 4
        elif depth == 0 and i + 4 <= len(text) and text[i:i+4].upper() == ' OR ':
            current += ch
        else:
            current += ch
        i += 1
    if current.strip():
        parts.append(current.strip())
    return [p for p in parts if p]


def _find_insert_pos(sql):
    upper = sql.upper()
    for kw in [' ORDER BY ', ' GROUP BY ', ' LIMIT ', ' OFFSET ', ' HAVING ']:
        pos = upper.find(kw)
        if pos != -1:
            return pos
    for kw in ['\nORDER BY', '\nGROUP BY', '\nLIMIT', '\nOFFSET', '\nHAVING']:
        pos = upper.find(kw)
        if pos != -1:
            return pos
    return len(sql)
