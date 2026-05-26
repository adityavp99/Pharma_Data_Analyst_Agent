from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import quote

import sqlparse


DISALLOWED_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "REPLACE",
    "TRUNCATE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "VACUUM",
}


def validate_sql(sql: str) -> None:
    if not sql or not sql.strip():
        raise ValueError("SQL query is empty.")

    statements = [statement for statement in sqlparse.split(sql) if statement.strip()]
    if len(statements) != 1:
        raise ValueError("Only a single SQL statement is allowed.")

    parsed = sqlparse.parse(statements[0])
    if not parsed:
        raise ValueError("SQL could not be parsed.")

    statement = parsed[0]
    first_token = next((token for token in statement.tokens if not token.is_whitespace), None)
    first_value = first_token.value.upper() if first_token else ""
    if first_value not in {"SELECT", "WITH"}:
        raise ValueError("Only SELECT or WITH queries are allowed.")

    normalized = re.sub(r"'[^']*'|\"[^\"]*\"", " ", statements[0].upper())
    for keyword in DISALLOWED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            raise ValueError(f"Disallowed SQL keyword detected: {keyword}.")


def maybe_add_limit(sql: str, limit: int = 200) -> str:
    validate_sql(sql)
    stripped = sql.strip().rstrip(";")
    if re.search(r"\bLIMIT\s+\d+\s*$", stripped, flags=re.IGNORECASE):
        return stripped
    return f"{stripped}\nLIMIT {limit}"


def _readonly_uri(db_path: str | Path) -> str:
    resolved = Path(db_path).resolve()
    return f"file:{quote(str(resolved))}?mode=ro"


def run_readonly_sql(sql: str, db_path: str, max_rows: int = 200) -> dict[str, Any]:
    try:
        limited_sql = maybe_add_limit(sql, max_rows)
        with sqlite3.connect(_readonly_uri(db_path), uri=True) as conn:
            cursor = conn.execute(limited_sql)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description or []]
        truncated = len(rows) >= max_rows
        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "sql_executed": limited_sql,
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "sql_executed": sql,
        }
