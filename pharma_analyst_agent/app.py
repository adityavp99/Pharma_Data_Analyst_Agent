from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.chart_vision import infer_chart_plan_from_screenshot
from agent.orchestrator import answer_question
from agent.response_formatter import summarize_python_result
from config import LLM_PROVIDER, OPENROUTER_API_KEY, PROCESSED_DATA_DIR
from tools.csv_tool import load_csv_to_sqlite, safe_table_name
from tools.schema_tool import get_table_row_counts


def _result_frame(result: dict[str, Any]) -> pd.DataFrame:
    sql_result = result.get("sql_result") or {}
    return pd.DataFrame(sql_result.get("rows", []), columns=sql_result.get("columns", []))


def _chart_frame(result: dict[str, Any]) -> pd.DataFrame:
    chart_plan = result.get("chart_plan") or {}
    source = chart_plan.get("source")
    if source == "python_result.trend":
        return pd.DataFrame((result.get("python_result") or {}).get("trend", []))
    if source == "python_result.percentage_change":
        return pd.DataFrame((result.get("python_result") or {}).get("percentage_change", []))
    if source == "python_result.outliers":
        return pd.DataFrame((result.get("python_result") or {}).get("outliers", []))
    return _result_frame(result)


def render_chart(result: dict[str, Any]) -> None:
    chart_plan = result.get("chart_plan")
    if not chart_plan:
        st.info("No chart is recommended for this response.")
        return

    frame = _chart_frame(result)
    if frame.empty:
        st.info("No chart data is available for this response.")
        return

    x_col = chart_plan["x_col"]
    y_col = chart_plan["y_col"]
    group_by = chart_plan.get("group_by")
    chart_type = chart_plan["chart_type"]
    if x_col not in frame.columns or y_col not in frame.columns:
        st.info("The chart recommendation does not match the returned data.")
        return

    frame = frame.copy()
    frame[y_col] = pd.to_numeric(frame[y_col], errors="coerce")
    if "month" in frame.columns:
        frame["month"] = pd.to_datetime(frame["month"], errors="coerce")
    if "_period" in frame.columns:
        frame["_period"] = pd.to_datetime(frame["_period"], errors="coerce")

    x_type = "T" if x_col in {"month", "_period", "result_date", "event_date"} else "N" if pd.api.types.is_numeric_dtype(frame[x_col]) else "O"
    tooltip_cols = [
        col
        for col in frame.columns
        if col in {x_col, y_col, group_by, "country", "region", "trial_id", "drug_name", "test_name"}
    ]
    base = alt.Chart(frame).encode(
        x=alt.X(f"{x_col}:{x_type}", title=x_col.replace("_", " ").title()),
        y=alt.Y(f"{y_col}:Q", title=y_col.replace("_", " ").title()),
        tooltip=tooltip_cols,
    )
    if group_by and group_by in frame.columns:
        base = base.encode(color=alt.Color(f"{group_by}:N", title=group_by.replace("_", " ").title()))

    if chart_type == "line":
        chart = base.mark_line(point=True)
    elif chart_type == "scatter":
        chart = base.mark_circle(size=90)
    else:
        chart = base.mark_bar()
    st.altair_chart(chart.properties(title=chart_plan.get("title", "Chart")), use_container_width=True)


def render_python_result(result: dict[str, Any]) -> None:
    python_result = result.get("python_result")
    if not python_result:
        st.info("No Python post-processing was needed.")
        return

    st.write(summarize_python_result(python_result))

    if "trend" in python_result:
        st.dataframe(pd.DataFrame(python_result["trend"]).head(30), hide_index=True, use_container_width=True)
        st.caption("Showing the first 30 trend rows. The chart tab is the preferred view for end users.")
    elif "percentage_change" in python_result:
        st.dataframe(pd.DataFrame(python_result["percentage_change"]).head(30), hide_index=True, use_container_width=True)
        st.caption("Showing the first 30 percentage-change rows. The chart tab is the preferred view for end users.")
    elif "outliers" in python_result:
        st.dataframe(pd.DataFrame(python_result["outliers"]).head(50), hide_index=True, use_container_width=True)
        st.caption("Showing up to 50 detected outlier rows.")
    elif "correlation" in python_result:
        st.metric("Correlation", python_result.get("correlation"))
        st.caption("Correlation is descriptive only and does not imply causality.")
    else:
        st.json(python_result)

    with st.expander("Raw Python output for debugging", expanded=False):
        st.json(python_result)


st.set_page_config(page_title="CSV Analyst Agent Lab", layout="wide")
st.title("CSV Analyst Agent Lab")
st.caption("Upload a CSV and ask open-ended analytical questions. This mode requires a working LLM provider.")

st.subheader("Data source")
uploaded_csv = st.file_uploader("Upload a CSV to test agentic analysis on your own data", type=["csv"])
uploaded_chart = st.file_uploader("Optional: upload a Tableau/chart screenshot to mimic", type=["png", "jpg", "jpeg"])

provider_note = LLM_PROVIDER
if LLM_PROVIDER == "openai" and not OPENROUTER_API_KEY:
    provider_note = "openai"
elif LLM_PROVIDER == "openai" and OPENROUTER_API_KEY:
    provider_note = "openrouter auto-selected because OPENROUTER_API_KEY is present"
st.info(f"Configured LLM provider: {provider_note}")

active_db_path = None
force_llm_planner = False
uploaded_info = None
if uploaded_csv is not None:
    table_name = safe_table_name(uploaded_csv.name)
    uploaded_db_path = PROCESSED_DATA_DIR / "uploaded_runtime.db"
    uploaded_csv.seek(0)
    uploaded_info = load_csv_to_sqlite(uploaded_csv, uploaded_db_path, table_name=table_name)
    active_db_path = uploaded_db_path
    force_llm_planner = True
    st.success(
        f"Using uploaded CSV table `{table_name}` with {uploaded_info['rows']:,} rows and "
        f"{len(uploaded_info['columns'])} columns. LLM-first planning is enabled for this file."
    )
else:
    st.warning("Upload a CSV to begin. The synthetic pharma templates are hidden in this focused agentic test mode.")
    st.stop()

with st.sidebar:
    st.subheader("Uploaded CSV")
    if active_db_path is not None:
        counts = get_table_row_counts(active_db_path)
        st.dataframe(pd.DataFrame([{"table": key, "rows": value} for key, value in counts.items()]), hide_index=True)
    if uploaded_info:
        st.write("Columns")
        st.write(uploaded_info["columns"])

question = st.text_area(
    "Ask a question about the uploaded CSV",
    placeholder=(
        "Examples:\n"
        "- What kind of data does this file contain? Show me sample rows and columns.\n"
        "- Summarize this file so I know what questions to ask.\n"
        "- Show total sales by product.\n"
        "- Create a line chart of revenue by month grouped by region."
    ),
    height=150,
)

if st.button("Analyze", type="primary") and question:
    with st.spinner("Routing tools and analyzing data..."):
        result = answer_question(question, active_db_path, force_llm_planner=True)

    if uploaded_chart is not None and result.get("sql_result") and "error" not in result["sql_result"]:
        image_bytes = uploaded_chart.getvalue()
        columns = result["sql_result"].get("columns", [])
        try:
            screenshot_plan = infer_chart_plan_from_screenshot(image_bytes, columns, question)
            if screenshot_plan:
                result["chart_plan"] = screenshot_plan
                st.info("Chart plan was guided by the uploaded screenshot.")
        except Exception as exc:
            st.warning(f"Could not use screenshot for chart planning: {exc}")

    if result.get("business_summary"):
        st.success(result["business_summary"])

    if result.get("planner_source") == "llm_failed":
        st.error("LLM was not used successfully. The agentic task failed and no unrelated fallback answer was returned.")

    st.markdown(result["answer"])

    tabs = st.tabs(["Chart", "Result table", "How it worked", "SQL", "Semantic context", "Python"])

    with tabs[0]:
        render_chart(result)

    with tabs[1]:
        if result.get("sql_result") and "error" not in result["sql_result"]:
            st.dataframe(
                _result_frame(result),
                hide_index=True,
                use_container_width=True,
            )
        elif result.get("sql_result", {}).get("error"):
            st.error(result["sql_result"]["error"])
        else:
            st.info("No SQL table was needed for this question.")

    with tabs[2]:
        st.write("The app uses a simple agent workflow:")
        st.write("1. Load the uploaded CSV into a temporary SQLite table.")
        st.write("2. Send the CSV schema and sample rows to the configured LLM.")
        st.write("3. Ask the LLM to generate one safe SQLite SELECT/WITH query.")
        st.write("4. Validate the SQL before execution.")
        st.write("5. Render answer, SQL, table, and chart if the LLM plan succeeds.")
        st.write(f"Planner source: `{result.get('planner_source', 'not applicable')}`")
        st.json(result.get("routing", {}))
        if result.get("chart_plan"):
            st.write("Chart recommendation:")
            st.json(result["chart_plan"])

    with tabs[3]:
        if result.get("sql_result", {}).get("sql_executed"):
            st.code(result["sql_result"]["sql_executed"], language="sql")
        elif result.get("sql"):
            st.code(result["sql"], language="sql")
        else:
            st.info("No SQL was used.")

    with tabs[4]:
        st.text(result.get("semantic_context") or "No semantic context was needed.")

    with tabs[5]:
        render_python_result(result)
