from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.orchestrator import answer_question
from agent.tool_router import route_question
from scripts.generate_synthetic_data import generate
from scripts.load_sqlite import DB_PATH, load_database


def _ensure_db() -> None:
    generate()
    load_database()


def test_router_flags_sales_trend_as_sql_then_python() -> None:
    route = route_question("Show monthly net sales trend by drug")
    assert route["needs_sql"] is True
    assert route["needs_python"] is True


def test_router_flags_sold_most_as_sql() -> None:
    route = route_question("Which drug was sold the most?")
    assert route["needs_sql"] is True
    assert route["analysis_type"] in {"sql_only", "semantic_sql"}


def test_router_refuses_medical_advice() -> None:
    route = route_question("Which drug should this patient take?")
    assert route["refuse"] is True


def test_sample_enrollment_question_runs() -> None:
    _ensure_db()
    result = answer_question("Which trials have the highest enrollment rate?", DB_PATH)
    assert "sql_result" in result
    assert "error" not in result["sql_result"]
    assert result["sql_result"]["row_count"] > 0
    assert "enrollment_rate_pct" in result["sql_result"]["columns"]


def test_sample_semantic_question_runs() -> None:
    result = answer_question("What does enrollment rate mean?", DB_PATH)
    assert result["routing"]["analysis_type"] == "semantic_only"
    assert "enrollment_rate" in result["answer"]


def test_sample_sold_most_question_runs() -> None:
    _ensure_db()
    result = answer_question("Which drug was sold the most?", DB_PATH)
    assert "sql_result" in result
    assert "error" not in result["sql_result"]
    assert result["sql_result"]["row_count"] > 0
    assert result["sql_result"]["columns"][:2] == ["drug_name", "units_sold"]
    assert "was sold the most" in result["answer"]


def test_sample_trend_question_returns_chart_plan() -> None:
    _ensure_db()
    result = answer_question("Show monthly net sales trend by drug.", DB_PATH)
    assert result["routing"]["needs_python"] is True
    assert result["python_result"] is not None
    assert "trend" in result["python_result"]
    assert result["chart_plan"]["chart_type"] == "line"
    assert result["chart_plan"]["source"] == "python_result.trend"


def test_sample_correlation_question_uses_python_correlation() -> None:
    _ensure_db()
    result = answer_question("What is the correlation between enrolled patients and adverse event count?", DB_PATH)
    assert result["routing"]["needs_python"] is True
    assert result["python_result"] is not None
    assert "correlation" in result["python_result"]
    assert result["python_result"]["rows_used"] == 30
