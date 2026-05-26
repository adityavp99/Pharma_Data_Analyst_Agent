from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from agent.llm_summary import summarize_for_business_user
from agent.response_formatter import format_final_answer
from agent.sql_planner import plan_query
from agent.tool_router import route_question
from tools.python_tool import (
    calculate_correlation,
    calculate_percentage_change,
    calculate_summary_statistics,
    calculate_trend,
    detect_simple_outliers,
)
from tools.schema_tool import get_schema_text
from tools.semantic_tool import get_relevant_semantic_context
from tools.sql_tool import run_readonly_sql


def _mentions(question: str, *terms: str) -> bool:
    q = question.lower()
    return any(term in q for term in terms)


def _extract_limit(question: str, default: int = 10) -> int:
    match = re.search(r"\btop\s+(\d+)|\bbottom\s+(\d+)|\blimit\s+(\d+)", question.lower())
    if not match:
        return default
    return min(max(int(next(group for group in match.groups() if group)), 1), 200)


def generate_sql_plan(user_question: str) -> dict[str, Any]:
    question = user_question.lower()
    limit = _extract_limit(user_question)

    if _mentions(question, "enrollment rate"):
        grain = "t.trial_id, t.drug_name, t.therapeutic_area"
        return {
            "sql": f"""
SELECT
  {grain},
  SUM(s.enrolled_patients) AS enrolled_patients,
  SUM(s.enrollment_target) AS enrollment_target,
  ROUND(100.0 * SUM(s.enrolled_patients) / NULLIF(SUM(s.enrollment_target), 0), 2) AS enrollment_rate_pct
FROM sites s
JOIN trials t ON t.trial_id = s.trial_id
GROUP BY {grain}
ORDER BY enrollment_rate_pct DESC
LIMIT {limit}
""".strip(),
            "explanation": "Enrollment rate is calculated as total enrolled patients divided by total enrollment target.",
            "assumptions": ["Grouped by trial because no other grain was explicitly requested."],
            "python": None,
        }

    if _mentions(question, "enrollment gap", "under enrolled", "under-enrolled"):
        return {
            "sql": f"""
SELECT
  t.trial_id,
  t.drug_name,
  t.therapeutic_area,
  SUM(s.enrollment_target) AS enrollment_target,
  SUM(s.enrolled_patients) AS enrolled_patients,
  SUM(s.enrollment_target) - SUM(s.enrolled_patients) AS enrollment_gap
FROM sites s
JOIN trials t ON t.trial_id = s.trial_id
GROUP BY t.trial_id, t.drug_name, t.therapeutic_area
ORDER BY enrollment_gap DESC
LIMIT {limit}
""".strip(),
            "explanation": "Enrollment gap is target minus enrolled patients; larger positive values indicate bigger shortfalls.",
            "assumptions": ["Grouped by trial."],
            "python": None,
        }

    if _mentions(question, "serious") and _mentions(question, "adverse", "ae"):
        return {
            "sql": f"""
SELECT
  t.trial_id,
  t.drug_name,
  t.therapeutic_area,
  COUNT(*) AS serious_ae_count,
  COUNT(DISTINCT ae.patient_id) AS patients_with_serious_ae
FROM adverse_events ae
JOIN trials t ON t.trial_id = ae.trial_id
WHERE ae.seriousness = 'Serious'
GROUP BY t.trial_id, t.drug_name, t.therapeutic_area
ORDER BY serious_ae_count DESC
LIMIT {limit}
""".strip(),
            "explanation": "Serious adverse events are counted where seriousness equals 'Serious'.",
            "assumptions": ["This is a descriptive count and does not imply causality."],
            "python": None,
        }

    if _mentions(question, "ae rate", "adverse event rate", "adverse events per patient"):
        return {
            "sql": f"""
SELECT
  t.trial_id,
  t.drug_name,
  COUNT(ae.ae_id) AS adverse_event_count,
  COUNT(DISTINCT p.patient_id) AS patient_count,
  ROUND(1.0 * COUNT(ae.ae_id) / NULLIF(COUNT(DISTINCT p.patient_id), 0), 3) AS ae_rate_per_patient
FROM patients p
LEFT JOIN adverse_events ae ON ae.patient_id = p.patient_id
JOIN trials t ON t.trial_id = p.trial_id
GROUP BY t.trial_id, t.drug_name
ORDER BY ae_rate_per_patient DESC
LIMIT {limit}
""".strip(),
            "explanation": "AE rate per patient is adverse event count divided by distinct synthetic patients.",
            "assumptions": ["Observation windows are not normalized in this MVP."],
            "python": None,
        }

    if _mentions(question, "out-of-range", "out of range", "lab"):
        group_clause = "lr.test_name"
        return {
            "sql": f"""
SELECT
  {group_clause},
  COUNT(*) AS lab_result_count,
  SUM(CASE WHEN lr.result_value < lr.normal_low OR lr.result_value > lr.normal_high THEN 1 ELSE 0 END) AS out_of_range_count,
  ROUND(100.0 * SUM(CASE WHEN lr.result_value < lr.normal_low OR lr.result_value > lr.normal_high THEN 1 ELSE 0 END) / COUNT(*), 2) AS out_of_range_rate_pct
FROM lab_results lr
GROUP BY {group_clause}
ORDER BY out_of_range_rate_pct DESC
LIMIT {limit}
""".strip(),
            "explanation": "Out-of-range lab rate is the share of lab results below normal_low or above normal_high.",
            "assumptions": ["Grouped by lab test because no trial or country grain was specified."],
            "python": None,
        }

    if _mentions(question, "trend", "growth", "percentage change", "percent change") and _mentions(question, "sales", "net sales", "sold"):
        python_plan = {"function": "calculate_trend", "arguments": {"date_col": "month", "value_col": "net_sales", "group_by": "drug_name"}}
        if _mentions(question, "percentage change", "percent change", "growth"):
            python_plan = {"function": "calculate_percentage_change", "arguments": {"date_col": "month", "value_col": "net_sales", "group_by": "drug_name"}}
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
        }

    if _mentions(question, "correlation"):
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
        }

    if _mentions(question, "outlier", "outliers"):
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
        }

    if _mentions(question, "drug") and _mentions(question, "net sales", "revenue", "sales") and _mentions(
        question, "highest", "top", "most", "largest", "maximum"
    ):
        return {
            "sql": f"""
SELECT
  drug_name,
  ROUND(SUM(net_sales), 2) AS net_sales,
  SUM(units_sold) AS units_sold,
  ROUND(SUM(net_sales) / NULLIF(SUM(units_sold), 0), 2) AS net_sales_per_unit
FROM drug_sales
GROUP BY drug_name
ORDER BY net_sales DESC
LIMIT {limit}
""".strip(),
            "explanation": "The drug with the highest net sales is determined by summing net_sales across all countries, channels, and months.",
            "assumptions": ["Using all available months and all sales channels."],
            "python": None,
        }

    if _mentions(question, "drug") and _mentions(question, "sold", "sell", "selling", "units sold", "most sold"):
        return {
            "sql": f"""
SELECT
  drug_name,
  SUM(units_sold) AS units_sold,
  ROUND(SUM(net_sales), 2) AS net_sales,
  ROUND(SUM(net_sales) / NULLIF(SUM(units_sold), 0), 2) AS net_sales_per_unit
FROM drug_sales
GROUP BY drug_name
ORDER BY units_sold DESC
LIMIT {limit}
""".strip(),
            "explanation": "The drug sold the most is determined by summing units_sold across all countries, channels, and months.",
            "assumptions": ["Interpreted 'sold the most' as highest total units_sold, not highest net sales."],
            "python": None,
        }

    if _mentions(question, "sales", "net sales", "units sold", "revenue"):
        value = "units_sold" if "units" in question else "net_sales"
        if _mentions(question, "sold", "sell", "selling"):
            value = "units_sold"
        order_col = value
        return {
            "sql": f"""
SELECT
  drug_name,
  country,
  region,
  SUM(units_sold) AS units_sold,
  ROUND(SUM(net_sales), 2) AS net_sales,
  ROUND(SUM(net_sales) / NULLIF(SUM(units_sold), 0), 2) AS net_sales_per_unit
FROM drug_sales
GROUP BY drug_name, country, region
ORDER BY {order_col} DESC
LIMIT {limit}
""".strip(),
            "explanation": "Sales are aggregated by drug, country, and region.",
            "assumptions": ["Using all available months unless the user specifies a date range."],
            "python": None,
        }

    return {
        "sql": f"""
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
LIMIT {limit}
""".strip(),
        "explanation": "Default summary by therapeutic area because the question did not match a more specific template.",
        "assumptions": ["Defaulted to a therapeutic-area summary."],
        "python": None,
    }


def _run_python_plan(sql_result: dict[str, Any], python_plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not python_plan:
        return None
    function_name = python_plan["function"]
    args = python_plan.get("arguments", {})
    if function_name == "calculate_trend":
        return calculate_trend(sql_result, **args)
    if function_name == "calculate_correlation":
        return calculate_correlation(sql_result, **args)
    if function_name == "calculate_percentage_change":
        return calculate_percentage_change(sql_result, **args)
    if function_name == "calculate_summary_statistics":
        return calculate_summary_statistics(sql_result, **args)
    if function_name == "detect_simple_outliers":
        return detect_simple_outliers(sql_result, **args)
    raise ValueError(f"Unsupported Python analysis function: {function_name}")


def _recommend_chart(sql_result: dict[str, Any] | None, python_result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if python_result and "trend" in python_result:
        return {
            "source": "python_result.trend",
            "chart_type": "line",
            "x_col": "_period",
            "y_col": python_result.get("value_col", "net_sales"),
            "group_by": python_result.get("group_by"),
            "title": "Trend over time",
        }
    if python_result and "percentage_change" in python_result:
        return {
            "source": "python_result.percentage_change",
            "chart_type": "line",
            "x_col": python_result.get("date_col", "month"),
            "y_col": "percentage_change",
            "group_by": python_result.get("group_by"),
            "title": "Percentage change over time",
        }
    if python_result and "outliers" in python_result:
        return {
            "source": "python_result.outliers",
            "chart_type": "bar",
            "x_col": "month",
            "y_col": "net_sales",
            "group_by": "drug_name",
            "title": "Detected outlier rows",
        }
    if not sql_result or "error" in sql_result or not sql_result.get("rows"):
        return None

    columns = sql_result.get("columns", [])
    numeric_priority = [
        "units_sold",
        "net_sales",
        "enrollment_rate_pct",
        "serious_ae_count",
        "out_of_range_rate_pct",
        "adverse_event_count",
        "patient_count",
    ]
    dimension_priority = ["drug_name", "trial_id", "test_name", "therapeutic_area", "country", "region", "month"]
    y_col = next((col for col in numeric_priority if col in columns), None)
    x_col = next((col for col in dimension_priority if col in columns), None)
    if not x_col or not y_col:
        return None
    chart_type = "line" if x_col == "month" else "bar"
    return {
        "source": "sql_result",
        "chart_type": chart_type,
        "x_col": x_col,
        "y_col": y_col,
        "group_by": "drug_name" if x_col == "month" and "drug_name" in columns else None,
        "title": f"{y_col} by {x_col}",
    }


def answer_question(user_question: str, db_path: str | Path) -> dict[str, Any]:
    routing = route_question(user_question)
    semantic_context = get_relevant_semantic_context(user_question) if routing["needs_semantic_context"] else ""
    schema_text = get_schema_text(db_path) if routing["needs_sql"] else ""

    if routing["refuse"] or routing["analysis_type"] == "semantic_only":
        answer = format_final_answer(user_question, routing, semantic_context, None, None, "")
        return {
            "answer": answer,
            "routing": routing,
            "semantic_context": semantic_context,
            "schema_text": schema_text,
            "chart_plan": None,
        }

    plan = plan_query(user_question, db_path)
    sql_result = run_readonly_sql(plan["sql"], str(db_path), max_rows=plan.get("max_rows", 200))
    python_result = None
    if routing["needs_python"] and "error" not in sql_result:
        python_result = _run_python_plan(sql_result, plan.get("python"))

    answer = format_final_answer(
        user_question=user_question,
        routing_decision=routing,
        semantic_context=semantic_context,
        sql=plan["sql"],
        sql_result=sql_result,
        explanation=plan["explanation"],
        assumptions=plan["assumptions"],
        python_result=python_result,
    )
    business_summary = None
    try:
        business_summary = summarize_for_business_user(user_question, sql_result, answer)
    except Exception as exc:
        business_summary = f"OpenRouter summary unavailable: {exc}"
    return {
        "answer": answer,
        "business_summary": business_summary,
        "routing": routing,
        "semantic_context": semantic_context,
        "schema_text": schema_text,
        "sql": plan["sql"],
        "sql_result": sql_result,
        "python_result": python_result,
        "chart_plan": _recommend_chart(sql_result, python_result),
        "planner_source": plan.get("planner_source", "unknown"),
    }
