from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import yaml


SEMANTIC_DIR = Path(__file__).resolve().parents[1] / "semantic_layer"
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "mean",
    "of",
    "or",
    "show",
    "the",
    "to",
    "what",
    "where",
    "which",
    "with",
}


def _load_yaml(file_name: str) -> dict[str, Any]:
    with open(SEMANTIC_DIR / file_name, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_metric_definitions() -> dict[str, Any]:
    return _load_yaml("metric_definitions.yaml")


def load_ontology() -> dict[str, Any]:
    return _load_yaml("ontology.yaml")


def load_business_glossary() -> dict[str, Any]:
    return _load_yaml("business_glossary.yaml")


def load_join_paths() -> dict[str, Any]:
    return _load_yaml("join_paths.yaml")


def get_metric_definition(metric_name: str) -> dict[str, Any] | None:
    metrics = load_metric_definitions()
    normalized = metric_name.lower().strip().replace(" ", "_")
    return metrics.get(normalized)


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if token not in STOPWORDS}


def _score_entry(query_tokens: set[str], key: str, entry: Any) -> int:
    haystack = f"{key} {entry}".lower().replace("_", " ")
    haystack_tokens = _tokens(haystack)
    return len(query_tokens & haystack_tokens)


def search_semantic_layer(query: str) -> dict[str, Any]:
    query_tokens = _tokens(query.replace("_", " "))
    results: dict[str, Any] = {"metrics": {}, "ontology": {}, "glossary": {}, "join_paths": {}}

    for key, entry in load_metric_definitions().items():
        exact = key.replace("_", " ") in query.lower().replace("-", " ")
        if exact or _score_entry(query_tokens, key, entry) >= 2:
            results["metrics"][key] = entry

    for key, entry in load_ontology().items():
        exact = key.lower() in query.lower()
        if exact or _score_entry(query_tokens, key, entry) >= 2:
            results["ontology"][key] = entry

    for key, entry in load_business_glossary().items():
        exact = key.lower() in query.lower().replace("-", " ")
        if exact or _score_entry(query_tokens, key, entry) >= 2:
            results["glossary"][key] = entry

    for key, entry in load_join_paths().get("relationships", {}).items():
        if _score_entry(query_tokens, key, entry) >= 2:
            results["join_paths"][key] = entry

    return results


def get_relevant_semantic_context(user_question: str) -> str:
    results = search_semantic_layer(user_question)
    sections: list[str] = []
    metrics = results.get("metrics", {})
    if metrics:
        sections.append("Metrics:")
        for key, value in metrics.items():
            sections.append(f"- {key}: {value.get('description', '')}")
            if value.get("formula"):
                sections.append(f"  Formula: {value['formula']}")
            for caution in value.get("cautions", []):
                sections.append(f"  Caution: {caution}")

    glossary = results.get("glossary", {})
    if glossary:
        sections.append("Glossary:")
        for key, value in glossary.items():
            sections.append(f"- {key}: {value.get('definition', '')}")
            for caution in value.get("cautions", []):
                sections.append(f"  Caution: {caution}")

    ontology = results.get("ontology", {})
    if ontology:
        sections.append("Business entities:")
        for key, value in ontology.items():
            table = value.get("source_table", "unknown")
            sections.append(f"- {key}: {value.get('description', '')} Source table: {table}.")

    join_paths = results.get("join_paths", {})
    if join_paths:
        sections.append("Join paths:")
        for key, value in join_paths.items():
            sections.append(f"- {key}: {value.get('join_condition', '')}")
            if value.get("caution"):
                sections.append(f"  Caution: {value['caution']}")
    return "\n".join(sections) if sections else "No directly matching semantic context found."
