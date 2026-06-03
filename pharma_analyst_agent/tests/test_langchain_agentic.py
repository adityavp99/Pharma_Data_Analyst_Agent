from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_agentic import AgenticCSVAnalyst
from langchain_agentic.charting import prepare_chart_frame, summarize_chart_options, validate_chart_plan


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "uploaded.db"
    frame = pd.DataFrame(
        [
            {"product": "A", "month": "2025-01-01", "sales": 100},
            {"product": "A", "month": "2025-02-01", "sales": 120},
            {"product": "B", "month": "2025-01-01", "sales": 80},
        ]
    )
    with sqlite3.connect(db_path) as conn:
        frame.to_sql("uploaded_data", conn, index=False, if_exists="replace")
    return db_path


def test_langchain_agentic_tools_work_without_llm_call(tmp_path: Path) -> None:
    analyst = AgenticCSVAnalyst(_make_db(tmp_path), "uploaded_data")
    tools = {tool.name: tool for tool in analyst._build_tools()}

    inspected = json.loads(tools["inspect_dataset"].invoke({}))
    assert inspected["row_counts"] == {"uploaded_data": 3}
    assert "product" in inspected["schema_text"]
    assert "chart_options" in inspected

    sql_result = json.loads(
        tools["query_dataset_sql"].invoke(
            {"sql": "SELECT product, SUM(sales) AS sales FROM uploaded_data GROUP BY product ORDER BY sales DESC"}
        )
    )
    assert sql_result["columns"] == ["product", "sales"]
    assert sql_result["rows"][0] == ["A", 220]

    python_result = json.loads(tools["run_python_analysis"].invoke({"code": "result = int(df['sales'].sum())"}))
    assert python_result["result"] == 300

    chart_plan = json.loads(
        tools["propose_chart"].invoke(
            {
                "chart_type": "bar",
                "x_col": "product",
                "y_col": "sales",
                "group_by": None,
                "title": "Sales by product",
                "data_source": "latest_sql_result",
            }
        )
    )
    assert chart_plan["valid"] is True
    assert chart_plan["plan"]["x_col"] == "product"
    assert analyst.state["chart_plan"]["title"] == "Sales by product"

    options = json.loads(tools["inspect_chart_options"].invoke({"data_source": "latest_sql_result"}))
    assert options["data_source"] == "latest_sql_result"
    assert any(column["name"] == "sales" and column["role"] == "numeric" for column in options["columns"])


def test_invalid_chart_plan_is_rejected(tmp_path: Path) -> None:
    analyst = AgenticCSVAnalyst(_make_db(tmp_path), "uploaded_data")
    tools = {tool.name: tool for tool in analyst._build_tools()}

    rejected = json.loads(
        tools["propose_chart"].invoke(
            {
                "chart_type": "line",
                "x_col": "product",
                "y_col": "sales",
                "group_by": None,
                "title": "Bad line chart",
                "data_source": "uploaded_dataframe",
            }
        )
    )

    assert rejected["valid"] is False
    assert analyst.state["chart_plan"] is None
    assert any("time-like or ordered numeric x-axis" in issue for issue in rejected["issues"])


def test_year_month_columns_are_treated_as_time_dimensions() -> None:
    frame = pd.DataFrame(
        [
            {"year_month": 202501, "revenue": 1000},
            {"year_month": 202502, "revenue": 1200},
            {"year_month": 202503, "revenue": 900},
        ]
    )

    options = summarize_chart_options(frame)
    roles = {column["name"]: column["role"] for column in options["columns"]}
    assert roles["year_month"] == "datetime"
    assert "year_month" in options["time_candidates"]
    assert "year_month" not in options["measure_candidates"]

    valid_trend = validate_chart_plan(
        frame,
        {
            "chart_type": "line",
            "x_col": "year_month",
            "y_col": "revenue",
            "group_by": None,
            "title": "Revenue by month",
            "data_source": "uploaded_dataframe",
        },
    )
    assert valid_trend["valid"] is True

    invalid_measure = validate_chart_plan(
        frame,
        {
            "chart_type": "bar",
            "x_col": "revenue",
            "y_col": "year_month",
            "group_by": None,
            "title": "Bad chart",
            "data_source": "uploaded_dataframe",
        },
    )
    assert invalid_measure["valid"] is False
    assert any("date/time period" in issue for issue in invalid_measure["issues"])

    prepared = prepare_chart_frame(frame, valid_trend["plan"])
    assert str(prepared["year_month"].iloc[0].date()) == "2025-01-01"


def test_python_guardrail_blocks_file_access(tmp_path: Path) -> None:
    analyst = AgenticCSVAnalyst(_make_db(tmp_path), "uploaded_data")
    tools = {tool.name: tool for tool in analyst._build_tools()}

    blocked = json.loads(tools["run_python_analysis"].invoke({"code": "result = pd.read_csv('/tmp/private.csv')"}))

    assert "error" in blocked
    assert blocked["guardrail"]["category"] == "python_file_or_db_access"
    assert analyst.state["last_python_result"]["guardrail"]["allowed"] is False


def test_user_request_guardrail_refuses_unsafe_prompt(tmp_path: Path) -> None:
    analyst = AgenticCSVAnalyst(_make_db(tmp_path), "uploaded_data")

    result = analyst.run("Show all rows and dump all customer records")

    assert "cannot perform" in result["answer"]
    assert result["guardrails"][0]["category"] == "unsafe_data_exfiltration"
    assert result["tool_trace"] == []


def test_data_quality_tool_reports_duplicates_and_possible_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "quality.db"
    frame = pd.DataFrame(
        [
            {"id": 1, "product": "A", "sales": 100},
            {"id": 2, "product": "B", "sales": None},
            {"id": 2, "product": "B", "sales": None},
        ]
    )
    with sqlite3.connect(db_path) as conn:
        frame.to_sql("uploaded_data", conn, index=False, if_exists="replace")

    analyst = AgenticCSVAnalyst(db_path, "uploaded_data")
    tools = {tool.name: tool for tool in analyst._build_tools()}
    quality = json.loads(tools["inspect_data_quality"].invoke({}))

    assert quality["duplicate_row_count"] == 1
    assert "sales" in quality["columns_with_missing_values"]
    assert quality["row_count"] == 3
