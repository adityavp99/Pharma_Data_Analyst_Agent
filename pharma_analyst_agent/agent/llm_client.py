from __future__ import annotations

from typing import Any
import json
import urllib.request

from openai import OpenAI

from config import (
    CUSTOM_OPENAI_API_KEY,
    CUSTOM_OPENAI_API_KEY_HEADER,
    CUSTOM_OPENAI_CHAT_URL,
    CUSTOM_OPENAI_MAX_TOKENS,
    CUSTOM_OPENAI_PLANNER_MODEL,
    CUSTOM_OPENAI_VISION_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_PLANNER_MODEL,
    OPENAI_VISION_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_PLANNER_MODEL,
    OPENROUTER_VISION_MODEL,
)


def _custom_chat_completion(messages: list[dict[str, Any]], temperature: float, model: str) -> str:
    headers = {
        "Content-Type": "application/json",
        CUSTOM_OPENAI_API_KEY_HEADER: CUSTOM_OPENAI_API_KEY,
    }
    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "top_p": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "max_tokens": CUSTOM_OPENAI_MAX_TOKENS,
    }
    if model:
        payload["model"] = model

    request = urllib.request.Request(
        CUSTOM_OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        response_json = json.loads(response.read().decode("utf-8"))
    return response_json["choices"][0]["message"]["content"]


def get_llm_client() -> tuple[OpenAI | None, str, str]:
    effective_provider = LLM_PROVIDER
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY and OPENROUTER_API_KEY:
        effective_provider = "openrouter"

    if effective_provider == "custom_openai":
        if not CUSTOM_OPENAI_CHAT_URL or not CUSTOM_OPENAI_API_KEY:
            return None, "", "custom_openai"
        return None, CUSTOM_OPENAI_PLANNER_MODEL, "custom_openai"

    if effective_provider == "openrouter":
        if not OPENROUTER_API_KEY:
            return None, "", "openrouter"
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1"), OPENROUTER_PLANNER_MODEL, "openrouter"

    if not OPENAI_API_KEY:
        return None, "", "openai"
    return OpenAI(api_key=OPENAI_API_KEY), OPENAI_PLANNER_MODEL, "openai"


def get_vision_client() -> tuple[OpenAI | None, str, str]:
    effective_provider = LLM_PROVIDER
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY and OPENROUTER_API_KEY:
        effective_provider = "openrouter"

    if effective_provider == "custom_openai":
        if not CUSTOM_OPENAI_CHAT_URL or not CUSTOM_OPENAI_API_KEY:
            return None, "", "custom_openai"
        return None, CUSTOM_OPENAI_VISION_MODEL, "custom_openai"

    if effective_provider == "openrouter":
        if not OPENROUTER_API_KEY:
            return None, "", "openrouter"
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1"), OPENROUTER_VISION_MODEL, "openrouter"

    if not OPENAI_API_KEY:
        return None, "", "openai"
    return OpenAI(api_key=OPENAI_API_KEY), OPENAI_VISION_MODEL, "openai"


def complete_chat(messages: list[dict[str, Any]], temperature: float = 0, vision: bool = False) -> tuple[str | None, str]:
    client, model, provider = get_vision_client() if vision else get_llm_client()

    if provider == "custom_openai":
        if not CUSTOM_OPENAI_CHAT_URL or not CUSTOM_OPENAI_API_KEY:
            return None, provider
        return _custom_chat_completion(messages, temperature, model), provider

    if client is None:
        return None, provider

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages,
    )
    return response.choices[0].message.content, provider
