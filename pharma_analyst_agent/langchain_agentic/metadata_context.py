from __future__ import annotations

import re
from typing import Any

import sqlparse


METRIC_TERMS = {
    "mat": "Moving annual total / last 12 months, depending on local business definition.",
    "mqt": "Moving quarterly total / recent quarter window, depending on local business definition.",
    "ytd": "Year to date.",
    "qtd": "Quarter to date.",
    "mtd": "Month to date.",
    "trx": "Total prescriptions or transactions, depending on local business definition.",
    "nrx": "New prescriptions, depending on local business definition.",
    "nbrx": "New-to-brand prescriptions, depending on local business definition.",
}


def _strip_sql_comments(sql_text: str) -> str:
    return sqlparse.format(sql_text, strip_comments=True)


def _dedupe(items: list[str], limit: int = 50) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = item.strip().strip('"[]`')
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _clip(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 20].rstrip() + " ...[truncated]"


def _extract_table_refs(sql_text: str) -> list[str]:
    pattern = re.compile(
        r"\b(?:from|join|into|update)\s+([a-zA-Z_][\w.$]*(?:\.[a-zA-Z_][\w.$]*)?)",
        re.IGNORECASE,
    )
    return _dedupe(pattern.findall(sql_text), limit=80)


def _extract_ctes(sql_text: str) -> list[str]:
    matches = re.findall(r"(?:with|,)\s+([a-zA-Z_][\w$]*)\s+as\s*\(", sql_text, flags=re.IGNORECASE)
    return _dedupe(matches, limit=50)


def _extract_alias_calculations(sql_text: str) -> list[dict[str, str]]:
    calculations: list[dict[str, str]] = []
    for match in re.finditer(
        r"(?P<expr>(?:case\b.*?\bend|sum\s*\(.*?\)|avg\s*\(.*?\)|count\s*\(.*?\)|max\s*\(.*?\)|min\s*\(.*?\)|coalesce\s*\(.*?\)|round\s*\(.*?\)|[\w.]+\s*[-+*/]\s*[\w.]+))\s+as\s+(?P<alias>[a-zA-Z_][\w$]*)",
        sql_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        calculations.append(
            {
                "alias": match.group("alias"),
                "expression": _clip(match.group("expr"), 600),
            }
        )
        if len(calculations) >= 80:
            break
    return calculations


def _extract_where_filters(sql_text: str) -> list[str]:
    filters: list[str] = []
    for match in re.finditer(
        r"\bwhere\b(?P<where>.*?)(?:\bgroup\s+by\b|\border\s+by\b|\bhaving\b|\bqualify\b|;|$)",
        sql_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        filters.append(_clip(match.group("where"), 800))
        if len(filters) >= 30:
            break
    return filters


def _extract_metric_snippets(sql_text: str) -> list[dict[str, str]]:
    snippets: list[dict[str, str]] = []
    lowered_terms = "|".join(re.escape(term) for term in METRIC_TERMS)
    for match in re.finditer(rf"(?<![a-zA-Z0-9])({lowered_terms})(?:\b|_)", sql_text, flags=re.IGNORECASE):
        start = max(match.start() - 350, 0)
        end = min(match.end() + 350, len(sql_text))
        term = match.group(1).lower()
        snippets.append(
            {
                "term": term,
                "default_hint": METRIC_TERMS.get(term, ""),
                "sql_snippet": _clip(sql_text[start:end], 700),
            }
        )
        if len(snippets) >= 30:
            break
    return snippets


def summarize_sql_context(sql_text: str, source_name: str = "uploaded_sql", max_raw_chars: int = 12000) -> dict[str, Any]:
    cleaned = _strip_sql_comments(sql_text)
    statements = [statement for statement in sqlparse.split(cleaned) if statement.strip()]
    return {
        "source_name": source_name,
        "statement_count": len(statements),
        "tables_or_views_referenced": _extract_table_refs(cleaned),
        "cte_names": _extract_ctes(cleaned),
        "calculated_fields_or_aliases": _extract_alias_calculations(cleaned),
        "filters_or_where_clauses": _extract_where_filters(cleaned),
        "metric_term_snippets": _extract_metric_snippets(cleaned),
        "raw_sql_excerpt": cleaned[:max_raw_chars],
        "notes_for_agent": [
            "Treat this as business/metadata context, not as SQL to execute directly.",
            "Use calculated_fields_or_aliases and metric_term_snippets to infer KPI definitions.",
            "Use filters_or_where_clauses as hints for dashboard filters or default business cuts.",
            "If a DML table/view name differs from the uploaded CSV table, map by column names and business meaning.",
            "If Tableau calculations conflict with this SQL context, state the assumption and limitation.",
        ],
    }
