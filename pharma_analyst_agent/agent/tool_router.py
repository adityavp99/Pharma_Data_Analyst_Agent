from __future__ import annotations

from typing import Any
import re

from tools.semantic_tool import search_semantic_layer


SQL_TERMS = [
    "count",
    "counts",
    "total",
    "sum",
    "average",
    "avg",
    "rank",
    "ranking",
    "top",
    "bottom",
    "most",
    "least",
    "max",
    "maximum",
    "min",
    "minimum",
    "filter",
    "compare",
    "comparison",
    "by",
    "group",
    "rate",
    "percentage",
    "proportion",
    "highest",
    "lowest",
    "sales",
    "sale",
    "sold",
    "sell",
    "selling",
    "revenue",
    "enrollment",
    "adverse",
    "lab",
]
PYTHON_TERMS = [
    "trend",
    "correlation",
    "correlate",
    "outlier",
    "outliers",
    "summary statistics",
    "statistical summary",
    "percentage change",
    "percent change",
    "growth",
    "month over month",
    "quarter over quarter",
]
DEFINITION_TERMS = ["define", "definition", "what is", "what does", "meaning of", "explain metric"]
UNSAFE_MEDICAL_TERMS = [
    "medical advice",
    "diagnose",
    "diagnosis",
    "treatment recommendation",
    "what should patient",
    "which drug should",
    "prove causality",
    "caused by the drug",
    "is caused by",
]


def route_question(user_question: str) -> dict[str, Any]:
    question = user_question.lower().strip()

    if any(term in question for term in UNSAFE_MEDICAL_TERMS):
        return {
            "needs_sql": False,
            "needs_python": False,
            "needs_semantic_context": False,
            "refuse": True,
            "refusal_reason": "The question asks for medical advice, diagnosis, treatment recommendation, or causal safety claims.",
            "analysis_type": "refusal",
            "rationale": "The MVP can provide descriptive analytics only, not medical or causal conclusions.",
        }

    semantic_matches = search_semantic_layer(user_question)
    needs_semantic = any(semantic_matches.values()) or "why" in question
    definition_phrase = any(term in question for term in DEFINITION_TERMS)
    analytical_phrase = any(
        term in question
        for term in [
            " by ",
            "show",
            "list",
            "calculate",
            "which",
            "top",
            "bottom",
            "highest",
            "lowest",
            "count",
            "trend",
            "compare",
            "sold",
            "sales",
            "rate by",
        ]
    )
    definition_only = definition_phrase and needs_semantic and not analytical_phrase
    needs_python = any(term in question for term in PYTHON_TERMS)
    needs_sql = any(re.search(rf"\b{re.escape(term)}\b", question) for term in SQL_TERMS)

    if definition_only:
        return {
            "needs_sql": False,
            "needs_python": False,
            "needs_semantic_context": True,
            "refuse": False,
            "refusal_reason": "",
            "analysis_type": "semantic_only",
            "rationale": "The question is asking for a business or metric definition.",
        }

    if needs_python:
        needs_sql = True

    if "why" in question:
        needs_sql = True
        needs_semantic = True

    # Semantic matches should enrich analytical questions, not replace SQL. Only
    # true definition-style questions should stop at the semantic layer.
    if needs_semantic and not definition_only and not needs_sql and not needs_python:
        needs_sql = True

    if needs_semantic and needs_sql and needs_python:
        analysis_type = "semantic_sql_python"
    elif needs_semantic and needs_sql:
        analysis_type = "semantic_sql"
    elif needs_sql and needs_python:
        analysis_type = "sql_python"
    elif needs_sql:
        analysis_type = "sql_only"
    elif needs_semantic:
        analysis_type = "semantic_only"
    else:
        needs_sql = True
        analysis_type = "sql_only"

    return {
        "needs_sql": needs_sql,
        "needs_python": needs_python,
        "needs_semantic_context": needs_semantic,
        "refuse": False,
        "refusal_reason": "",
        "analysis_type": analysis_type,
        "rationale": "Deterministic keyword routing selected the minimum tools needed for the question.",
    }
