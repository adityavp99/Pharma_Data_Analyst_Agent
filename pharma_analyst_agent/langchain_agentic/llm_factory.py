from __future__ import annotations

from urllib.parse import urlparse

from config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_PLANNER_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_PLANNER_MODEL,
)


class LangChainAgentError(RuntimeError):
    pass


def _openrouter_base_url() -> str:
    parsed = urlparse(OPENROUTER_BASE_URL)
    if parsed.path.endswith("/chat/completions"):
        return OPENROUTER_BASE_URL[: -len("/chat/completions")]
    return OPENROUTER_BASE_URL.rstrip("/")


def build_chat_model():
    try:
        from langchain_openai import AzureChatOpenAI, ChatOpenAI
    except ImportError as exc:
        raise LangChainAgentError(
            "LangChain dependencies are not installed. Run `pip install -r requirements.txt` "
            "inside the pharma_analyst_agent environment."
        ) from exc

    if LLM_PROVIDER == "azure_openai":
        if not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT:
            raise LangChainAgentError(
                "Azure OpenAI is selected, but AZURE_OPENAI_API_KEY, "
                "AZURE_OPENAI_ENDPOINT, or AZURE_OPENAI_DEPLOYMENT is missing."
            )
        return AzureChatOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_deployment=AZURE_OPENAI_DEPLOYMENT,
            api_version=AZURE_OPENAI_API_VERSION,
            api_key=AZURE_OPENAI_API_KEY,
            temperature=0,
        )

    if LLM_PROVIDER == "openrouter":
        if not OPENROUTER_API_KEY:
            raise LangChainAgentError("OpenRouter is selected, but OPENROUTER_API_KEY is missing.")
        return ChatOpenAI(
            model=OPENROUTER_PLANNER_MODEL,
            api_key=OPENROUTER_API_KEY,
            base_url=_openrouter_base_url(),
            temperature=0,
        )

    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise LangChainAgentError("OpenAI is selected, but OPENAI_API_KEY is missing.")
        return ChatOpenAI(
            model=OPENAI_PLANNER_MODEL,
            api_key=OPENAI_API_KEY,
            temperature=0,
        )

    raise LangChainAgentError(
        f"`{LLM_PROVIDER}` is not supported by the LangChain agent yet. "
        "Use LLM_PROVIDER=azure_openai, openai, or openrouter."
    )
