from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from openai import OpenAI

from agent.context_builder import build_llm_context
from config import ENABLE_LLM_PLANNER, OPENROUTER_API_KEY, OPENROUTER_PLANNER_MODEL
from tools.metric_sql_builder import build_metric_plan_from_question
from tools.sql_tool import validate_sql


APPROVED_PYTHON_FUNCTIONS = {
    "calculate_correlation",
    "calculate_summary_statistics",
    "calculate_trend",
    "calculate_percentage_change",
    "detect_simple_outliers",
    "create_chart_data",
}


def _mentions(question: str, *terms: str) -> bool:
    q = question.lower()
    return any(term in q for term in terms)


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalize_python_plan(plan: dict[str, Any]) -> dict[str, Any] | None:
    if not plan.get("needs_python_analysis"):
        return None
    recommended = plan.get("recommended_python_analysis") or {}
    function_name = recommended.get("function_name") or recommended.get("function")
    if function_name not in APPROVED_PYTHON_FUNCTIONS:
        return None
    return {"function": function_name, "arguments": recommended.get("arguments", {})}


def _llm_plan(user_question: str, db_path: str | Path) -> dict[str, Any] | None:
    if not ENABLE_LLM_PLANNER or not OPENROUTER_API_KEY:
        return None

    context = build_llm_context(user_question, db_path)
    client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    response = client.chat.completions.create(
        model=OPENROUTER_PLANNER_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a SQL planning agent for synthetic pharma analytics. "
                    "Return only JSON. Generate one SQLite SELECT or WITH query only. "
                    "Use only the provided tables, columns, metric definitions, and join paths. "
                    "Prefer aggregate outputs. Do not output patient-level details unless explicitly necessary. "
                    "For adverse event analysis, do not infer causality."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {user_question}\n\n"
                    f"{context['combined_context']}\n\n"
                    "Return JSON with this shape:\n"
                    "{\n"
                    '  "sql": "...",\n'
                    '  "explanation": "...",\n'
                    '  "assumptions": ["..."],\n'
                    '  "needs_python_analysis": false,\n'
                    '  "recommended_python_analysis": {"function_name": "", "arguments": {}}\n'
                    "}"
                ),
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    parsed = _extract_json(content)
    sql = parsed.get("sql", "")
    validate_sql(sql)
    return {
        "sql": sql,
        "explanation": parsed.get("explanation", "LLM planner generated SQL using semantic and schema context."),
        "assumptions": parsed.get("assumptions", []),
        "python": _normalize_python_plan(parsed),
        "planner_source": "llm_openrouter",
    }


def _python_first_plan(user_question: str) -> dict[str, Any] | None:
    if _mentions(user_question, "trend", "growth", "percentage change", "percent change") and _mentions(
        user_question, "sales", "net sales", "sold"
    ):
        python_plan = {
            "function": "calculate_trend",
            "arguments": {"date_col": "month", "value_col": "net_sales", "group_by": "drug_name"},
        }
        if _mentions(user_question, "percentage change", "percent change", "growth"):
            python_plan = {
                "function": "calculate_percentage_change",
                "arguments": {"date_col": "month", "value_col": "net_sales", "group_by": "drug_name"},
            }
        return {
            "sql": """
SELECT
  drug_name,
  month,
  SUM(net_sales) AS net_sales
FROM drug_sales
GROUP BY drug_name, month
ORDER BY drug_name, month
LIMIT 1000
""".strip(),
            "explanation": "Monthly net sales are aggregated by drug, then controlled Python computes the requested time-series analysis.",
            "assumptions": ["Sales currency is USD in the synthetic dataset."],
            "python": python_plan,
            "max_rows": 1000,
            "planner_source": "python_analysis_template",
        }

    if _mentions(user_question, "correlation"):
        return {
            "sql": """
WITH site_agg AS (
  SELECT
    trial_id,
    SUM(enrollment_target) AS enrollment_target,
    SUM(enrolled_patients) AS enrolled_patients
  FROM sites
  GROUP BY trial_id
),
ae_agg AS (
  SELECT
    trial_id,
    COUNT(ae_id) AS adverse_event_count
  FROM adverse_events
  GROUP BY trial_id
)
SELECT
  s.trial_id,
  s.enrollment_target,
  s.enrolled_patients,
  COALESCE(a.adverse_event_count, 0) AS adverse_event_count
FROM site_agg s
LEFT JOIN ae_agg a ON a.trial_id = s.trial_id
""".strip(),
            "explanation": "The query prepares trial-level enrollment and adverse event counts for correlation analysis.",
            "assumptions": ["Correlation is descriptive and does not imply causality."],
            "python": {
                "function": "calculate_correlation",
                "arguments": {"x_col": "enrolled_patients", "y_col": "adverse_event_count"},
            },
            "planner_source": "python_analysis_template",
        }

    if _mentions(user_question, "outlier", "outliers"):
        return {
            "sql": """
SELECT
  drug_name,
  country,
  month,
  SUM(net_sales) AS net_sales
FROM drug_sales
GROUP BY drug_name, country, month
ORDER BY net_sales DESC
LIMIT 2000
""".strip(),
            "explanation": "The query aggregates monthly sales so the controlled Python tool can flag simple IQR outliers.",
            "assumptions": ["Using net_sales as the outlier value because no other value was specified."],
            "python": {"function": "detect_simple_outliers", "arguments": {"value_col": "net_sales"}},
            "max_rows": 2000,
            "planner_source": "python_analysis_template",
        }

    return None


def _fallback_portfolio_plan() -> dict[str, Any]:
    return {
        "sql": """
SELECT
  t.therapeutic_area,
  COUNT(DISTINCT t.trial_id) AS trial_count,
  COUNT(DISTINCT p.patient_id) AS patient_count,
  COUNT(DISTINCT ae.ae_id) AS adverse_event_count
FROM trials t
LEFT JOIN patients p ON p.trial_id = t.trial_id
LEFT JOIN adverse_events ae ON ae.trial_id = t.trial_id
GROUP BY t.therapeutic_area
ORDER BY trial_count DESC
LIMIT 10
""".strip(),
        "explanation": "Default portfolio summary by therapeutic area because no specific metric builder or LLM plan was available.",
        "assumptions": ["Defaulted to a therapeutic-area summary."],
        "python": None,
        "planner_source": "safe_fallback",
    }


def plan_query(user_question: str, db_path: str | Path) -> dict[str, Any]:
    python_plan = _python_first_plan(user_question)
    if python_plan:
        return python_plan

    metric_plan = build_metric_plan_from_question(user_question)
    if metric_plan:
        return metric_plan

    llm_plan = _llm_plan(user_question, db_path)
    if llm_plan:
        return llm_plan

    return _fallback_portfolio_plan()
