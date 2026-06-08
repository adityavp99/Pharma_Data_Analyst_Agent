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
from langchain_agentic.agent import _diagnostic_result
from langchain_agentic.charting import build_plotly_chart, prepare_chart_frame, summarize_chart_options, validate_chart_plan
from langchain_agentic.metadata_context import summarize_sql_context


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
    assert "uploaded_data" in inspected["chart_options_by_table"]

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


def test_multi_series_chart_plan_is_supported() -> None:
    frame = pd.DataFrame(
        [
            {"year_month": 202501, "actual": 1000, "target": 900, "previous": 850},
            {"year_month": 202502, "actual": 1200, "target": 950, "previous": 900},
        ]
    )

    plan = {
        "chart_type": "line",
        "x_col": "year_month",
        "y_col": ["actual", "target", "previous"],
        "group_by": None,
        "title": "Sales value trend",
        "data_source": "latest_sql_result",
        "color_map": {"actual": "#e31a1c", "target": "#000000", "previous": "#d0d0d0"},
    }

    validation = validate_chart_plan(frame, plan)
    assert validation["valid"] is True
    figure = build_plotly_chart(frame, plan)
    assert len(figure.data) == 3


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

    table_quality = quality["tables"]["uploaded_data"]
    assert table_quality["duplicate_row_count"] == 1
    assert "sales" in table_quality["columns_with_missing_values"]
    assert table_quality["row_count"] == 3


def test_column_values_tool_validates_requested_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "filters.db"
    frame = pd.DataFrame(
        [
            {"geography_lvl1": "Australia", "brand": "DARZALEX", "sales": 100},
            {"geography_lvl1": "Australia", "brand": "OTHER", "sales": 50},
            {"geography_lvl1": "Japan", "brand": "DARZALEX", "sales": 80},
        ]
    )
    with sqlite3.connect(db_path) as conn:
        frame.to_sql("uploaded_data", conn, index=False, if_exists="replace")

    analyst = AgenticCSVAnalyst(db_path, "uploaded_data")
    tools = {tool.name: tool for tool in analyst._build_tools()}

    result = json.loads(
        tools["inspect_column_values"].invoke(
            {
                "column_names": ["geography_lvl1", "brand", "missing_column"],
                "search_value": "Aus",
                "max_values_per_column": 10,
            }
        )
    )

    assert result["tables"]["uploaded_data"]["columns"]["geography_lvl1"]["values"][0]["value"] == "Australia"
    assert result["tables"]["uploaded_data"]["columns"]["missing_column"]["error"]


def test_agent_can_inspect_multiple_uploaded_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "multi.db"
    sales = pd.DataFrame(
        [
            {"product_id": 1, "year_month": 202501, "sales_value": 100},
            {"product_id": 2, "year_month": 202501, "sales_value": 50},
        ]
    )
    products = pd.DataFrame(
        [
            {"product_id": 1, "brand": "DARZALEX"},
            {"product_id": 2, "brand": "OTHER"},
        ]
    )
    with sqlite3.connect(db_path) as conn:
        sales.to_sql("sales", conn, index=False, if_exists="replace")
        products.to_sql("products", conn, index=False, if_exists="replace")

    analyst = AgenticCSVAnalyst(db_path, ["sales", "products"])
    tools = {tool.name: tool for tool in analyst._build_tools()}

    inspected = json.loads(tools["inspect_dataset"].invoke({}))
    assert inspected["row_counts"] == {"products": 2, "sales": 2}
    assert inspected["primary_table"] == "sales"
    assert "products" in inspected["profiles_by_table"]

    sql_result = json.loads(
        tools["query_dataset_sql"].invoke(
            {
                "sql": (
                    "SELECT p.brand, SUM(s.sales_value) AS sales_value "
                    "FROM sales s JOIN products p ON s.product_id = p.product_id "
                    "GROUP BY p.brand"
                )
            }
        )
    )
    assert sql_result["columns"] == ["brand", "sales_value"]
    assert sql_result["rows"][0] == ["DARZALEX", 100]


def test_tool_events_are_recorded_for_diagnostics(tmp_path: Path) -> None:
    analyst = AgenticCSVAnalyst(_make_db(tmp_path), "uploaded_data")
    tools = {tool.name: tool for tool in analyst._build_tools()}

    tools["query_dataset_sql"].invoke({"sql": "SELECT product, SUM(sales) AS sales FROM uploaded_data GROUP BY product"})

    events = analyst.state["tool_events"]
    assert any(event["tool"] == "query_dataset_sql" and event["status"] == "started" for event in events)
    assert any(event["tool"] == "query_dataset_sql" and event["status"] == "success" for event in events)


def test_sql_context_parser_extracts_tables_metrics_and_filters() -> None:
    sql = """
    CREATE TABLE dashboard_sales AS
    SELECT
      product_name,
      country,
      SUM(CASE WHEN period_rank <= 12 THEN trx ELSE 0 END) AS mat_trx,
      SUM(CASE WHEN period_rank <= 3 THEN trx ELSE 0 END) AS mqt_trx
    FROM commercial.sales_mart
    WHERE country = 'US' AND channel = 'Retail'
    GROUP BY product_name, country;
    """

    context = summarize_sql_context(sql, source_name="tableau_source.sql")

    assert "commercial.sales_mart" in context["tables_or_views_referenced"]
    assert any(item["alias"] == "mat_trx" for item in context["calculated_fields_or_aliases"])
    assert any(item["term"] == "mat" for item in context["metric_term_snippets"])
    assert any("country" in item.lower() for item in context["filters_or_where_clauses"])


def test_business_context_tool_returns_uploaded_dml_context(tmp_path: Path) -> None:
    context = summarize_sql_context("SELECT SUM(trx) AS mat_trx FROM sales WHERE country = 'US'")
    analyst = AgenticCSVAnalyst(
        _make_db(tmp_path),
        "uploaded_data",
        business_context=context,
        dashboard_context="Default front-end filter: country=US",
    )
    tools = {tool.name: tool for tool in analyst._build_tools()}

    result = json.loads(tools["inspect_business_context"].invoke({}))

    assert "dml_or_sql_context" in result
    assert result["dashboard_or_filter_notes"] == "Default front-end filter: country=US"
    assert any(item["alias"] == "mat_trx" for item in result["dml_or_sql_context"]["calculated_fields_or_aliases"])


def test_recursion_diagnostic_result_includes_trace_and_causes(tmp_path: Path) -> None:
    analyst = AgenticCSVAnalyst(_make_db(tmp_path), "uploaded_data")
    analyst.state["tool_events"] = [
        {"tool": "propose_chart", "status": "validation_failed", "details": {"issues": ["bad chart"]}},
        {"tool": "propose_chart", "status": "validation_failed", "details": {"issues": ["bad chart"]}},
        {"tool": "propose_chart", "status": "validation_failed", "details": {"issues": ["bad chart"]}},
    ]
    analyst.state["chart_validation"] = {"valid": False, "issues": ["bad chart"]}

    try:
        raise RuntimeError("recursion")
    except RuntimeError as exc:
        result = _diagnostic_result(
            question="make a chart",
            error=exc,
            error_type="recursion_limit",
            state=analyst.state,
            recursion_limit=20,
        )

    assert "recursion limit" in result["answer"].lower()
    assert result["diagnostics"]["error_type"] == "recursion_limit"
    assert result["diagnostics"]["tool_counts"]["propose_chart"] == 3
    assert "Traceback" in result["diagnostics"]["traceback"]
    assert any("Repeated tool calls" in cause for cause in result["diagnostics"]["likely_causes"])
