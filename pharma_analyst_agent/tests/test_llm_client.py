from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
