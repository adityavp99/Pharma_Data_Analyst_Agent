from __future__ import annotations

from typing import Any

from agent.llm_client import complete_chat
from config import AI_SUMMARY_PROVIDER, LLM_PROVIDER, OPENROUTER_API_KEY


def is_summary_enabled() -> bool:
    if AI_SUMMARY_PROVIDER == "llm":
        return True
    return AI_SUMMARY_PROVIDER == "openrouter" and bool(OPENROUTER_API_KEY)


def summarize_for_business_user(
    user_question: str,
    sql_result: dict[str, Any] | None,
    deterministic_answer: str,
) -> str | None:
    if not is_summary_enabled():
        return None

    content, _provider = complete_chat(
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You rewrite analytics results for a nontechnical business user. "
                    "Use only the numbers and facts provided. Do not invent numbers. "
                    "Keep it concise. Mention that the data is synthetic."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {user_question}\n\n"
                    f"SQL result: {sql_result}\n\n"
                    f"Draft answer: {deterministic_answer}"
                ),
            },
        ],
    )
    return content


def summarize_csv_result_for_user(
    user_question: str,
    sql_result: dict[str, Any] | None,
    sql: str | None,
) -> str | None:
    if not sql_result or "error" in sql_result:
        return None

    preview = {
        "columns": sql_result.get("columns", []),
        "row_count": sql_result.get("row_count", 0),
        "sample_rows": sql_result.get("rows", [])[:20],
        "sql": sql,
    }
    content, _provider = complete_chat(
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a CSV data analyst. Explain the query result to a nontechnical user. "
                    "Use only the provided columns, rows, and SQL. Do not invent facts. "
                    "If the user is asking what the file contains, describe the likely subject matter, "
                    "important columns, example values, and useful follow-up questions."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {user_question}\n\nResult preview: {preview}",
            },
        ],
    )
    return content
