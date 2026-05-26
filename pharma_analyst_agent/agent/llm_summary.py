from __future__ import annotations

from typing import Any

from openai import OpenAI

from config import AI_SUMMARY_PROVIDER, OPENROUTER_API_KEY, OPENROUTER_SUMMARY_MODEL


def is_summary_enabled() -> bool:
    return AI_SUMMARY_PROVIDER == "openrouter" and bool(OPENROUTER_API_KEY)


def summarize_for_business_user(
    user_question: str,
    sql_result: dict[str, Any] | None,
    deterministic_answer: str,
) -> str | None:
    if not is_summary_enabled():
        return None

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    completion = client.chat.completions.create(
        model=OPENROUTER_SUMMARY_MODEL,
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
        temperature=0,
    )
    return completion.choices[0].message.content
