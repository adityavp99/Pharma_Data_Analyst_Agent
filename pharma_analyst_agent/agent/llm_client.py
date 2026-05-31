from __future__ import annotations

from openai import OpenAI

from config import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_PLANNER_MODEL,
    OPENAI_VISION_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_PLANNER_MODEL,
    OPENROUTER_VISION_MODEL,
)


def get_llm_client() -> tuple[OpenAI | None, str, str]:
    if LLM_PROVIDER == "openrouter":
        if not OPENROUTER_API_KEY:
            return None, "", "openrouter"
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1"), OPENROUTER_PLANNER_MODEL, "openrouter"

    if not OPENAI_API_KEY:
        return None, "", "openai"
    return OpenAI(api_key=OPENAI_API_KEY), OPENAI_PLANNER_MODEL, "openai"


def get_vision_client() -> tuple[OpenAI | None, str, str]:
    if LLM_PROVIDER == "openrouter":
        if not OPENROUTER_API_KEY:
            return None, "", "openrouter"
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1"), OPENROUTER_VISION_MODEL, "openrouter"

    if not OPENAI_API_KEY:
        return None, "", "openai"
    return OpenAI(api_key=OPENAI_API_KEY), OPENAI_VISION_MODEL, "openai"
