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
