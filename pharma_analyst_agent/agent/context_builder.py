from __future__ import annotations

from pathlib import Path
from typing import Any
import sqlite3

from tools.schema_tool import get_schema
from tools.semantic_tool import get_relevant_semantic_context, load_join_paths


def build_compact_schema_context(db_path: str | Path, max_columns_per_table: int = 12) -> str:
    schema = get_schema(db_path)
    lines: list[str] = []
    for table_name, columns in schema.items():
        column_names = [column["name"] for column in columns[:max_columns_per_table]]
        lines.append(f"- {table_name}({', '.join(column_names)})")
    return "\n".join(lines)


def build_join_context(max_relationships: int = 12) -> str:
    relationships = load_join_paths().get("relationships", {})
    lines: list[str] = []
    for idx, (name, relationship) in enumerate(relationships.items()):
        if idx >= max_relationships:
            break
        lines.append(f"- {name}: {relationship.get('join_condition')}")
        if relationship.get("caution"):
            lines.append(f"  Caution: {relationship['caution']}")
    return "\n".join(lines)


def build_sample_rows_context(db_path: str | Path, max_rows: int = 5) -> str:
    schema = get_schema(db_path)
    lines: list[str] = []
    with sqlite3.connect(db_path) as conn:
        for table_name in schema:
            quoted_table = '"' + table_name.replace('"', '""') + '"'
            rows = conn.execute(f"SELECT * FROM {quoted_table} LIMIT ?", (max_rows,)).fetchall()
            columns = [column["name"] for column in schema[table_name]]
            lines.append(f"Table {table_name} sample rows:")
            for row in rows:
                preview = dict(zip(columns, row))
                lines.append(f"- {preview}")
    return "\n".join(lines)


def build_llm_context(user_question: str, db_path: str | Path, max_chars: int = 7000) -> dict[str, Any]:
    semantic_context = get_relevant_semantic_context(user_question)
    schema_context = build_compact_schema_context(db_path)
    join_context = build_join_context()
    sample_rows_context = build_sample_rows_context(db_path)
    combined = (
        "Relevant semantic context:\n"
        f"{semantic_context}\n\n"
        "Available schema:\n"
        f"{schema_context}\n\n"
        "Approved join paths:\n"
        f"{join_context}\n\n"
        "Sample rows:\n"
        f"{sample_rows_context}"
    )
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n...[context truncated]"
    return {
        "semantic_context": semantic_context,
        "schema_context": schema_context,
        "join_context": join_context,
        "sample_rows_context": sample_rows_context,
        "combined_context": combined,
    }
