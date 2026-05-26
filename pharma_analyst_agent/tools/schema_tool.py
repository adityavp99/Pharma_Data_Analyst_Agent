from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


def _connect(db_path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def get_schema(db_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    with _connect(db_path) as conn:
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        schema: dict[str, list[dict[str, Any]]] = {}
        for (table_name,) in table_rows:
            columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            schema[table_name] = [
                {
                    "cid": column[0],
                    "name": column[1],
                    "type": column[2],
                    "notnull": bool(column[3]),
                    "default_value": column[4],
                    "primary_key": bool(column[5]),
                }
                for column in columns
            ]
    return schema


def describe_table(table_name: str, db_path: str | Path, sample_rows: int = 5) -> dict[str, Any]:
    with _connect(db_path) as conn:
        columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        sample = conn.execute(f"SELECT * FROM {table_name} LIMIT ?", (sample_rows,)).fetchall()
        column_names = [column[1] for column in columns]
        return {
            "table": table_name,
            "columns": column_names,
            "column_details": columns,
            "sample_rows": [dict(zip(column_names, row)) for row in sample],
        }


def get_table_row_counts(db_path: str | Path) -> dict[str, int]:
    with _connect(db_path) as conn:
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return {
            table_name: conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            for (table_name,) in table_rows
        }


def get_schema_text(db_path: str | Path) -> str:
    schema = get_schema(db_path)
    lines: list[str] = []
    for table_name, columns in schema.items():
        lines.append(f"Table: {table_name}")
        for column in columns:
            column_type = column["type"] or "UNKNOWN"
            lines.append(f"  - {column['name']} ({column_type})")
    return "\n".join(lines)
