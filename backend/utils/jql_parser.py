from __future__ import annotations

import re

_CLAUSE_PATTERN = re.compile(
    r'(?i)^\s*(\w[\w\s]*?)\s+(NOT IN|!=|!~|IN|=|~)\s+(.+)\s*$'
)


def parse_jql(jql: str) -> list[dict[str, str | list[str]]]:
    clauses = re.split(r'\bAND\b', jql, flags=re.IGNORECASE)
    rows: list[dict[str, str | list[str]]] = []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        match = _CLAUSE_PATTERN.match(clause)
        if not match:
            raise ValueError(
                f"Cannot parse clause: '{clause}'. Expected: field OPERATOR value"
            )
        field_raw = match.group(1).strip()
        operator = match.group(2).upper()
        raw_value = match.group(3).strip()

        field = field_raw.title()

        if raw_value.startswith("("):
            inner = raw_value.strip("()")
            values = [v.strip().strip("'\"") for v in inner.split(",")]
        else:
            values = [raw_value.strip("'\"")]

        rows.append({"field": field, "operator": operator, "value": values})
    return rows
