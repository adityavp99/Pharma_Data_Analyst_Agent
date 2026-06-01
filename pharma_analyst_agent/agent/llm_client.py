from __future__ import annotations

from typing import Any
import json
import urllib.error
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
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
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


def _message_content_from_response(response_json: dict[str, Any], provider: str) -> str:
    if response_json.get("error"):
        raise RuntimeError(f"{provider} returned error: {response_json['error']}")

    choices = response_json.get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider} returned no choices. Response keys: {list(response_json.keys())}")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"{provider} returned no message object in first choice: {choices[0]}")

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        ]
        joined = "\n".join(part for part in text_parts if part).strip()
        if joined:
            return joined

    reasoning = message.get("reasoning") or message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning

    raise RuntimeError(
        f"{provider} returned an empty message content. "
        f"Try another model, or use a non-reasoning/chat model. Message keys: {list(message.keys())}"
    )


def _openrouter_chat_completion(messages: list[dict[str, Any]], temperature: float, model: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }
    if OPENROUTER_HTTP_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
    if OPENROUTER_APP_TITLE:
        headers["X-Title"] = OPENROUTER_APP_TITLE

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    request = urllib.request.Request(
        OPENROUTER_BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_json = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {body}") from exc
    return _message_content_from_response(response_json, "OpenRouter")


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
        return None, OPENROUTER_PLANNER_MODEL, "openrouter"

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
        return None, OPENROUTER_VISION_MODEL, "openrouter"

    if not OPENAI_API_KEY:
        return None, "", "openai"
    return OpenAI(api_key=OPENAI_API_KEY), OPENAI_VISION_MODEL, "openai"


def complete_chat(messages: list[dict[str, Any]], temperature: float = 0, vision: bool = False) -> tuple[str | None, str]:
    client, model, provider = get_vision_client() if vision else get_llm_client()

    if provider == "custom_openai":
        if not CUSTOM_OPENAI_CHAT_URL or not CUSTOM_OPENAI_API_KEY:
            return None, provider
        return _custom_chat_completion(messages, temperature, model), provider

    if provider == "openrouter":
        if not OPENROUTER_API_KEY:
            return None, provider
        return _openrouter_chat_completion(messages, temperature, model), provider

    if client is None:
        return None, provider

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"{provider} returned an empty message content.")
    return content, provider
