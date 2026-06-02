from __future__ import annotations

from pathlib import Path
from typing import Any
import sqlite3
import sys

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import LLM_PROVIDER, PROCESSED_DATA_DIR
from langchain_agentic import AgenticCSVAnalyst, LangChainAgentError
from tools.csv_tool import load_csv_to_sqlite, safe_table_name
from tools.schema_tool import get_table_row_counts


def _sql_result_frame(sql_result: dict[str, Any] | None) -> pd.DataFrame:
    if not sql_result or "error" in sql_result:
        return pd.DataFrame()
    return pd.DataFrame(sql_result.get("rows", []), columns=sql_result.get("columns", []))


def _uploaded_frame(db_path: Path, table_name: str, limit: int = 10000) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as conn:
        return pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT ?', conn, params=(limit,))


def _chart_source_frame(result: dict[str, Any], db_path: Path, table_name: str) -> pd.DataFrame:
    chart_plan = result.get("chart_plan") or {}
    if chart_plan.get("data_source") == "uploaded_dataframe":
        return _uploaded_frame(db_path, table_name)

    sql_frame = _sql_result_frame(result.get("last_sql_result"))
    if not sql_frame.empty:
        return sql_frame
    return _uploaded_frame(db_path, table_name)


def render_agent_chart(result: dict[str, Any], db_path: Path, table_name: str) -> None:
    chart_plan = result.get("chart_plan")
    if not chart_plan:
        st.info("The agent did not propose a chart for this answer.")
        return

    frame = _chart_source_frame(result, db_path, table_name)
    if frame.empty:
        st.info("There is no data available to render the proposed chart.")
        return

    x_col = chart_plan.get("x_col")
    y_col = chart_plan.get("y_col")
    group_by = chart_plan.get("group_by")
    chart_type = str(chart_plan.get("chart_type", "bar")).lower()

    if x_col not in frame.columns or y_col not in frame.columns:
        st.warning("The agent proposed chart columns that are not present in the available result data.")
        st.json(chart_plan)
        return

    frame = frame.copy()
    frame[y_col] = pd.to_numeric(frame[y_col], errors="coerce")
    parsed_x = pd.to_datetime(frame[x_col], errors="coerce")
    if parsed_x.notna().mean() > 0.8:
        frame[x_col] = parsed_x
        x_type = "T"
    elif pd.api.types.is_numeric_dtype(frame[x_col]):
        x_type = "Q"
    else:
        x_type = "N"

    tooltip = [col for col in [x_col, y_col, group_by] if col and col in frame.columns]
    base = alt.Chart(frame).encode(
        x=alt.X(f"{x_col}:{x_type}", title=str(x_col).replace("_", " ").title()),
        y=alt.Y(f"{y_col}:Q", title=str(y_col).replace("_", " ").title()),
        tooltip=tooltip,
    )
    if group_by and group_by in frame.columns:
        base = base.encode(color=alt.Color(f"{group_by}:N", title=str(group_by).replace("_", " ").title()))

    if chart_type == "line":
        chart = base.mark_line(point=True)
    elif chart_type == "scatter":
        chart = base.mark_circle(size=80)
    elif chart_type == "area":
        chart = base.mark_area(opacity=0.7)
    else:
        chart = base.mark_bar()

    st.altair_chart(chart.properties(title=chart_plan.get("title") or "Agent chart"), use_container_width=True)
    with st.expander("Chart spec chosen by the agent", expanded=False):
        st.json(chart_plan)


def render_trace(trace: list[dict[str, Any]]) -> None:
    if not trace:
        st.info("No tool calls were captured.")
        return
    for index, item in enumerate(trace, start=1):
        if item["type"] == "tool_call":
            st.markdown(f"**{index}. Tool call: `{item['tool']}`**")
            st.json(item.get("arguments"))
        else:
            st.markdown(f"**{index}. Tool result: `{item['tool']}`**")
            st.code(item.get("content_preview", ""), language="json")


st.set_page_config(page_title="LangChain Agentic CSV Analyst", layout="wide")
st.title("LangChain Agentic CSV Analyst")
st.caption(
    "Upload a CSV and ask a question. The LangChain agent decides whether to inspect data, run SQL, "
    "run pandas analysis, and propose a chart."
)

with st.sidebar:
    st.subheader("Runtime")
    st.write(f"LLM provider: `{LLM_PROVIDER}`")
    st.write("Architecture: `LangChain create_agent`")
    st.write("Mode: CSV-backed local SQLite")

uploaded_csv = st.file_uploader("Upload CSV", type=["csv"])
if uploaded_csv is None:
    st.info("Upload a CSV file to start the agentic workflow.")
    st.stop()

table_name = safe_table_name(uploaded_csv.name)
uploaded_db_path = PROCESSED_DATA_DIR / "agentic_uploaded_runtime.db"
uploaded_csv.seek(0)
uploaded_info = load_csv_to_sqlite(uploaded_csv, uploaded_db_path, table_name=table_name)

st.success(
    f"Loaded `{uploaded_csv.name}` as table `{table_name}` with "
    f"{uploaded_info['rows']:,} rows and {len(uploaded_info['columns'])} columns."
)

with st.expander("Uploaded data preview", expanded=True):
    st.dataframe(pd.DataFrame(uploaded_info["sample_rows"]), hide_index=True, use_container_width=True)
    st.write("Columns")
    st.write(uploaded_info["columns"])

with st.sidebar:
    st.subheader("Tables")
    counts = get_table_row_counts(uploaded_db_path)
    st.dataframe(pd.DataFrame([{"table": key, "rows": value} for key, value in counts.items()]), hide_index=True)

question = st.text_area(
    "Ask the agent a question about this CSV",
    placeholder=(
        "Examples:\n"
        "- What kind of data does this file contain?\n"
        "- Show me a useful summary and recommend questions I can ask.\n"
        "- Which product has the highest revenue and why?\n"
        "- Build a trend chart by month and explain the movement."
    ),
    height=150,
)

if st.button("Run agent", type="primary", disabled=not question.strip()):
    with st.spinner("The agent is reasoning and calling tools..."):
        try:
            analyst = AgenticCSVAnalyst(uploaded_db_path, table_name)
            result = analyst.run(question)
        except LangChainAgentError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error("The LangChain agentic task failed.")
            st.exception(exc)
            st.stop()

    st.subheader("Answer")
    st.markdown(result["answer"])

    tabs = st.tabs(["Chart", "Latest SQL Result", "Python Result", "Agent Trace", "Generated SQL"])

    with tabs[0]:
        render_agent_chart(result, uploaded_db_path, table_name)

    with tabs[1]:
        latest_sql = result.get("last_sql_result")
        if latest_sql and latest_sql.get("error"):
            st.error(latest_sql["error"])
        elif latest_sql:
            st.dataframe(_sql_result_frame(latest_sql), hide_index=True, use_container_width=True)
        else:
            st.info("The agent did not run SQL for this answer.")

    with tabs[2]:
        python_result = result.get("last_python_result")
        if python_result:
            st.json(python_result)
        else:
            st.info("The agent did not run Python for this answer.")

    with tabs[3]:
        render_trace(result.get("tool_trace", []))

    with tabs[4]:
        sql_queries = result.get("sql_queries", [])
        if sql_queries:
            for query in sql_queries:
                st.code(query, language="sql")
        else:
            st.info("No SQL was generated.")
