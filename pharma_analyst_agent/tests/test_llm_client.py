from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import llm_client
from agent.llm_client import _message_content_from_response


def test_message_content_from_openrouter_style_response() -> None:
    response = {"choices": [{"message": {"role": "assistant", "content": "{\"sql\":\"SELECT 1\"}"}}]}
    assert _message_content_from_response(response, "OpenRouter") == "{\"sql\":\"SELECT 1\"}"


def test_message_content_raises_clear_error_for_empty_message() -> None:
    response = {"choices": [{"message": {"role": "assistant", "content": None}}]}
    with pytest.raises(RuntimeError, match="empty message content"):
        _message_content_from_response(response, "OpenRouter")


def test_message_content_raises_clear_error_for_provider_error() -> None:
    response = {"error": {"message": "bad key"}}
    with pytest.raises(RuntimeError, match="returned error"):
        _message_content_from_response(response, "OpenRouter")


def test_get_llm_client_uses_azure_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    created = {}

    class FakeAzureOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr(llm_client, "LLM_PROVIDER", "azure_openai")
    monkeypatch.setattr(llm_client, "AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "AZURE_OPENAI_ENDPOINT", "https://example.com/openai-chat")
    monkeypatch.setattr(llm_client, "AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
    monkeypatch.setattr(llm_client, "AZURE_OPENAI_API_VERSION", "2024-10-21")
    monkeypatch.setattr(llm_client, "AzureOpenAI", FakeAzureOpenAI)

    client, model, provider = llm_client.get_llm_client()

    assert isinstance(client, FakeAzureOpenAI)
    assert model == "gpt-4o-mini"
    assert provider == "azure_openai"
    assert created == {
        "azure_endpoint": "https://example.com/openai-chat",
        "azure_deployment": "gpt-4o-mini",
        "api_key": "test-key",
        "api_version": "2024-10-21",
    }
