from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from agent.context_builder import build_llm_context
from agent.llm_client import complete_chat
from config import ENABLE_LLM_PLANNER
from tools.schema_tool import get_schema
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


def _llm_plan(user_question: str, db_path: str | Path, mode: str = "pharma") -> dict[str, Any] | None:
    if not ENABLE_LLM_PLANNER:
        return None

    context = build_llm_context(user_question, db_path)
    domain_instruction = (
        "You are a SQL planning agent for synthetic pharma analytics."
        if mode == "pharma"
        else "You are a SQL planning agent for a user-uploaded CSV loaded into SQLite."
    )
    content, provider = complete_chat(
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    f"{domain_instruction} "
                    "Return only JSON. Generate one SQLite SELECT or WITH query only. "
                    "Use only the provided tables and columns. "
                    "Use semantic metric definitions and join paths when provided. "
                    "Prefer aggregate outputs. Do not output patient-level details unless explicitly necessary. "
                    "For adverse event analysis, do not infer causality. "
                    "If a chart is requested, return SQL that provides the needed x/y/group fields. "
                    "If the user asks what the uploaded file contains, describe, preview, or summarize the columns, "
                    "generate a simple SELECT query that returns representative rows and useful columns."
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
    if content is None:
        raise RuntimeError(f"LLM provider '{provider}' was not configured or returned no content.")
    parsed = _extract_json(content)
    sql = parsed.get("sql", "")
    validate_sql(sql)
    return {
        "sql": sql,
        "explanation": parsed.get("explanation", "LLM planner generated SQL using semantic and schema context."),
        "assumptions": parsed.get("assumptions", []),
        "python": _normalize_python_plan(parsed),
        "planner_source": f"llm_{provider}",
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


def _fallback_uploaded_csv_plan(db_path: str | Path) -> dict[str, Any]:
    schema = get_schema(db_path)
    first_table = next(iter(schema), None)
    if not first_table:
        return _fallback_portfolio_plan()
    return {
        "sql": f"SELECT * FROM {first_table} LIMIT 20",
        "explanation": "No LLM plan was available, so the agent returned a preview of the uploaded CSV table.",
        "assumptions": ["Configure OPENAI_API_KEY or OPENROUTER_API_KEY to enable agentic SQL planning over uploaded CSV files."],
        "python": None,
        "planner_source": "uploaded_csv_preview_fallback",
    }


def plan_query(user_question: str, db_path: str | Path, force_llm_first: bool = False) -> dict[str, Any]:
    if force_llm_first:
        try:
            llm_plan = _llm_plan(user_question, db_path, mode="uploaded_csv")
        except Exception as exc:
            return {
                "error": (
                    "Agentic LLM planning failed for the uploaded CSV. "
                    "No fallback answer was used."
                ),
                "error_detail": str(exc),
                "planner_source": "llm_failed",
                "llm_used": False,
            }
        if llm_plan:
            llm_plan["llm_used"] = True
            return llm_plan
        return {
            "error": "Agentic LLM planning returned no plan for the uploaded CSV. No fallback answer was used.",
            "planner_source": "llm_failed",
            "llm_used": False,
        }

    python_plan = _python_first_plan(user_question)
    if python_plan:
        return python_plan

    metric_plan = build_metric_plan_from_question(user_question)
    if metric_plan:
        return metric_plan

    try:
        llm_plan = _llm_plan(user_question, db_path, mode="pharma")
    except Exception:
        llm_plan = None
    if llm_plan:
        return llm_plan

    return _fallback_portfolio_plan()
