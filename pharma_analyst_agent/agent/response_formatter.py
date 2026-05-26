from __future__ import annotations

from typing import Any


def _humanize_number(value: Any) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _rows_as_dicts(sql_result: dict[str, Any]) -> list[dict[str, Any]]:
    columns = sql_result.get("columns", [])
    return [dict(zip(columns, row)) for row in sql_result.get("rows", [])]


def summarize_python_result(python_result: dict[str, Any] | None) -> str:
    if not python_result:
        return ""

    if "trend" in python_result:
        rows = python_result.get("trend", [])
        groups = {
            row.get(python_result.get("group_by"))
            for row in rows
            if python_result.get("group_by") and row.get(python_result.get("group_by")) is not None
        }
        return (
            f"Python post-processing calculated a monthly trend with {len(rows):,} points"
            + (f" across {len(groups):,} groups." if groups else ".")
        )

    if "percentage_change" in python_result:
        rows = python_result.get("percentage_change", [])
        return f"Python post-processing calculated percentage change for {len(rows):,} time-series rows."

    if "outliers" in python_result:
        outliers = python_result.get("outliers", [])
        low = _humanize_number(python_result.get("low_threshold"))
        high = _humanize_number(python_result.get("high_threshold"))
        return (
            f"Python post-processing used the IQR method and found {len(outliers):,} outlier rows. "
            f"Values below {low} or above {high} were flagged."
        )

    if "correlation" in python_result:
        corr = python_result.get("correlation")
        corr_text = "not available" if corr is None else _humanize_number(corr)
        return (
            f"Python post-processing calculated a correlation of {corr_text} between "
            f"{python_result.get('x_col')} and {python_result.get('y_col')} "
            f"using {python_result.get('rows_used', 0):,} rows."
        )

    if "statistics" in python_result:
        return f"Python post-processing calculated summary statistics for {python_result.get('value_col')}."

    return "Python post-processing was completed."


def build_plain_english_summary(explanation: str, sql_result: dict[str, Any] | None) -> str:
    if not sql_result or "error" in sql_result or not sql_result.get("rows"):
        return explanation

    first = _rows_as_dicts(sql_result)[0]
    cols = set(first)

    if {"drug_name", "month", "net_sales"}.issubset(cols):
        row_count = sql_result.get("row_count", len(sql_result.get("rows", [])))
        return f"Monthly net sales were prepared for trend analysis across {row_count:,} drug-month rows."

    if {"drug_name", "net_sales"}.issubset(cols) and "units_sold" in cols and "net_sales_per_unit" in cols:
        if "sold" not in explanation.lower():
            return f"{first['drug_name']} had the highest net sales, at ${_humanize_number(first['net_sales'])} in the synthetic dataset."

    if {"drug_name", "units_sold"}.issubset(cols):
        return f"{first['drug_name']} was sold the most, with {_humanize_number(first['units_sold'])} units sold in the synthetic dataset."

    if {"drug_name", "net_sales"}.issubset(cols) and "units_sold" not in cols:
        return f"{first['drug_name']} had the highest net sales, at ${_humanize_number(first['net_sales'])} in the synthetic dataset."

    if {"trial_id", "enrollment_rate_pct"}.issubset(cols):
        return (
            f"{first['trial_id']} had the highest enrollment rate at "
            f"{_humanize_number(first['enrollment_rate_pct'])}%."
        )

    if {"trial_id", "serious_ae_count"}.issubset(cols):
        return (
            f"{first['trial_id']} had the highest serious adverse event count, "
            f"with {_humanize_number(first['serious_ae_count'])} serious adverse events."
        )

    if {"test_name", "out_of_range_rate_pct"}.issubset(cols):
        return (
            f"{first['test_name']} had the highest out-of-range lab rate at "
            f"{_humanize_number(first['out_of_range_rate_pct'])}%."
        )

    return explanation


def _format_rows(sql_result: dict[str, Any], max_rows: int = 10) -> str:
    if "error" in sql_result:
        return f"SQL error: {sql_result['error']}"
    columns = sql_result.get("columns", [])
    rows = sql_result.get("rows", [])
    if not rows:
        return "No rows returned."
    lines = [" | ".join(columns), " | ".join(["---"] * len(columns))]
    for row in rows[:max_rows]:
        lines.append(" | ".join(str(value) for value in row))
    if len(rows) > max_rows:
        lines.append(f"... {len(rows) - max_rows} more rows")
    return "\n".join(lines)


def format_final_answer(
    user_question: str,
    routing_decision: dict[str, Any],
    semantic_context: str,
    sql: str | None,
    sql_result: dict[str, Any] | None,
    explanation: str,
    assumptions: list[str] | None = None,
    python_result: dict[str, Any] | None = None,
) -> str:
    assumptions = assumptions or []
    if routing_decision.get("refuse"):
        return (
            "Answer:\n"
            f"I can't answer that as requested. {routing_decision.get('refusal_reason')}\n\n"
            "Safe analytical redirection:\n"
            "I can summarize descriptive synthetic counts, rates, and trends without making medical or causal claims."
        )

    if routing_decision.get("analysis_type") == "semantic_only":
        return (
            "Answer:\n"
            f"{semantic_context}\n\n"
            "Evidence:\n"
            "This answer comes from the local semantic layer, not a database query.\n\n"
            "Assumptions and limitations:\n"
            "Definitions are MVP business definitions for synthetic data analysis."
        )

    evidence = _format_rows(sql_result or {})
    answer_summary = build_plain_english_summary(explanation, sql_result)
    sql_text = sql_result.get("sql_executed", sql) if sql_result else sql
    py_summary = summarize_python_result(python_result)
    py_text = f"\n\nPython analysis:\n{py_summary}" if py_summary else ""
    limitation_lines = [
        "- Findings are based only on synthetic sample data.",
        "- The answer uses available structured fields only.",
        "- Adverse event outputs are descriptive and must not be interpreted as causal evidence.",
    ]
    limitation_lines.extend(f"- {item}" for item in assumptions)

    return (
        "Answer:\n"
        f"{answer_summary}\n\n"
        "Evidence:\n"
        f"{evidence}{py_text}\n\n"
        "Query or calculation used:\n"
        "The agent routed the question, applied any matching semantic definitions, executed read-only SQL, "
        "and used controlled Python only when extra post-query computation was required.\n\n"
        "SQL used:\n"
        f"```sql\n{sql_text or 'No SQL used.'}\n```\n\n"
        "Assumptions and limitations:\n"
        + "\n".join(limitation_lines)
    )
