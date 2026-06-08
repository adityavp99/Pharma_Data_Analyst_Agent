from __future__ import annotations

from pathlib import Path
from typing import Any
import base64
import sqlite3
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import LLM_PROVIDER, PROCESSED_DATA_DIR
from langchain_agentic import AgenticCSVAnalyst, LangChainAgentError
from langchain_agentic.charting import build_plotly_chart, validate_chart_plan
from langchain_agentic.metadata_context import summarize_sql_context
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
        if result.get("chart_validation"):
            st.write("Latest chart validation feedback:")
            st.json(result["chart_validation"])
        return

    frame = _chart_source_frame(result, db_path, table_name)
    if frame.empty:
        st.info("There is no data available to render the proposed chart.")
        return

    validation = validate_chart_plan(frame, chart_plan)
    if not validation["valid"]:
        st.warning("The proposed chart failed validation and was not rendered.")
        st.json(validation)
        return
    if validation["warnings"]:
        st.warning("Chart validation warnings: " + " ".join(validation["warnings"]))

    st.plotly_chart(build_plotly_chart(frame, chart_plan), use_container_width=True)
    with st.expander("Chart spec chosen by the agent", expanded=False):
        st.json(chart_plan)
        st.write("Validation")
        st.json(validation)


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


def render_result_details(result: dict[str, Any], db_path: Path, table_name: str) -> None:
    tabs = st.tabs(
        ["Chart", "Latest SQL Result", "Python Result", "Guardrails", "Diagnostics", "Agent Trace", "Generated SQL"]
    )

    with tabs[0]:
        render_agent_chart(result, db_path, table_name)

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
        guardrails = result.get("guardrails") or []
        if guardrails:
            st.json(guardrails)
        else:
            st.info("No guardrail interventions were triggered for this answer.")

    with tabs[4]:
        diagnostics = result.get("diagnostics")
        if diagnostics:
            st.write("Likely causes")
            for cause in diagnostics.get("likely_causes", []):
                st.write(f"- {cause}")
            st.write("Tool counts")
            st.json(diagnostics.get("tool_counts", {}))
            st.write("Recent tool events")
            st.json(diagnostics.get("recent_tool_events", []))
            with st.expander("Full diagnostic payload", expanded=False):
                st.json({key: value for key, value in diagnostics.items() if key != "traceback"})
            with st.expander("Traceback", expanded=False):
                st.code(diagnostics.get("traceback", ""), language="python")
        else:
            st.info("No runtime diagnostics were captured for this answer.")

    with tabs[5]:
        render_trace(result.get("tool_trace", []))

    with tabs[6]:
        sql_queries = result.get("sql_queries", [])
        if sql_queries:
            for query in sql_queries:
                st.code(query, language="sql")
        else:
            st.info("No SQL was generated.")


st.set_page_config(page_title="LangChain Agentic CSV Analyst", layout="wide")
st.title("LangChain Agentic CSV Analyst")
st.caption(
    "Upload a CSV and chat with a LangChain data analyst agent. The agent decides whether to inspect data, "
    "run SQL, run pandas analysis, and propose charts."
)

with st.sidebar:
    st.subheader("Runtime")
    st.write(f"LLM provider: `{LLM_PROVIDER}`")
    st.write("Architecture: `LangChain create_agent`")
    st.write("Mode: CSV-backed local SQLite")
    st.caption("Large CSV uploads are loaded into SQLite in chunks and reused during the chat session.")

uploaded_csv = st.file_uploader("Upload CSV", type=["csv"])
if uploaded_csv is None:
    st.info("Upload a CSV file to start the agentic workflow.")
    st.stop()

with st.sidebar:
    st.subheader("Optional Context")
    uploaded_sql = st.file_uploader(
        "Upload DML/SQL context",
        type=["sql", "txt"],
        help="Use this for MQT/MAT definitions, Tableau source SQL, calculated fields, and dashboard filters.",
    )
    uploaded_chart_image = st.file_uploader(
        "Upload Tableau/chart screenshot",
        type=["png", "jpg", "jpeg"],
        help="Works only if your configured model supports image input.",
    )
    dashboard_notes = st.text_area(
        "Dashboard/filter notes",
        placeholder="Example: Default filters are country=US, channel=Retail, time grain=month...",
        height=100,
    )
    chart_replication_notes = st.text_area(
        "Manual chart replication context",
        placeholder=(
            "Optional but useful when the screenshot is ambiguous.\n"
            "Example:\n"
            "Timeperiod = MTH\n"
            "geography_lvl1 = Australia\n"
            "brandgroup = overall / no filter\n"
            "TA = overall / no filter\n"
            "DA = overall / no filter\n"
            "x-axis = year_month\n"
            "y-axis = sales_value"
        ),
        height=170,
        help=(
            "Use this to state selected Tableau/frontend filters and chart fields. "
            "The agent should treat this as stronger evidence than screenshot inference."
        ),
    )

table_name = safe_table_name(uploaded_csv.name)
uploaded_db_path = PROCESSED_DATA_DIR / "agentic_uploaded_runtime.db"
uploaded_size = getattr(uploaded_csv, "size", None)
csv_source_signature = f"{uploaded_csv.name}:{uploaded_size}:{table_name}"
needs_csv_reload = (
    st.session_state.get("loaded_csv_source_signature") != csv_source_signature
    or st.session_state.get("loaded_csv_table_name") != table_name
    or not uploaded_db_path.exists()
)

if needs_csv_reload:
    uploaded_csv.seek(0)
    with st.spinner("Loading CSV into local SQLite. Large files can take a few minutes..."):
        uploaded_info = load_csv_to_sqlite(uploaded_csv, uploaded_db_path, table_name=table_name)
    st.session_state.loaded_csv_source_signature = csv_source_signature
    st.session_state.loaded_csv_table_name = table_name
    st.session_state.loaded_csv_info = uploaded_info
else:
    uploaded_info = st.session_state.loaded_csv_info

file_signature = f"{uploaded_csv.name}:{uploaded_info['rows']}:{','.join(uploaded_info['columns'])}"
dml_context: dict[str, Any] | None = None
if uploaded_sql is not None:
    sql_text = uploaded_sql.getvalue().decode("utf-8", errors="replace")
    dml_context = summarize_sql_context(sql_text, source_name=uploaded_sql.name)
    file_signature += f":sql:{uploaded_sql.name}:{len(sql_text)}"

visual_context = None
if uploaded_chart_image is not None:
    image_bytes = uploaded_chart_image.getvalue()
    visual_context = {
        "mime_type": uploaded_chart_image.type or "image/png",
        "image_bytes_b64": base64.b64encode(image_bytes).decode("utf-8"),
        "file_name": uploaded_chart_image.name,
    }
    file_signature += f":image:{uploaded_chart_image.name}:{len(image_bytes)}"

if dashboard_notes:
    file_signature += f":notes:{hash(dashboard_notes)}"
if chart_replication_notes:
    file_signature += f":chart_notes:{hash(chart_replication_notes)}"

if st.session_state.get("active_file_signature") != file_signature:
    st.session_state.active_file_signature = file_signature
    st.session_state.chat_messages = []
elif "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

st.success(
    f"Loaded `{uploaded_csv.name}` as table `{table_name}` with "
    f"{uploaded_info['rows']:,} rows and {len(uploaded_info['columns'])} columns."
)

with st.expander("Uploaded data preview", expanded=not st.session_state.get("chat_messages")):
    st.dataframe(pd.DataFrame(uploaded_info["sample_rows"]), hide_index=True, use_container_width=True)
    st.write("Columns")
    st.write(uploaded_info["columns"])

with st.sidebar:
    st.subheader("Tables")
    counts = get_table_row_counts(uploaded_db_path)
    st.dataframe(pd.DataFrame([{"table": key, "rows": value} for key, value in counts.items()]), hide_index=True)
    if dml_context:
        with st.expander("DML/SQL context summary", expanded=False):
            st.write("Tables/views referenced")
            st.write(dml_context.get("tables_or_views_referenced", []))
            st.write("Calculated fields / aliases")
            st.json(dml_context.get("calculated_fields_or_aliases", [])[:10])
            st.write("Metric snippets")
            st.json(dml_context.get("metric_term_snippets", [])[:10])
    if uploaded_chart_image is not None:
        st.caption(f"Screenshot attached: `{uploaded_chart_image.name}`")
    if st.button("Clear chat"):
        st.session_state.chat_messages = []
        st.rerun()

if not st.session_state.chat_messages:
    with st.chat_message("assistant"):
        st.markdown(
            "I loaded your CSV. Ask me what the file contains, what metrics matter, "
            "or request a specific analysis/chart."
        )

for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("result"):
            with st.expander("Analysis details", expanded=False):
                render_result_details(message["result"], uploaded_db_path, table_name)

prompt = st.chat_input(
    "Ask a follow-up or a new analytical question about the uploaded CSV..."
)

if prompt:
    history_for_agent = [
        {"role": message["role"], "content": message["content"]}
        for message in st.session_state.chat_messages
        if message["role"] in {"user", "assistant"}
    ]
    st.session_state.chat_messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("The agent is reasoning and calling tools..."):
            try:
                analyst = AgenticCSVAnalyst(
                    uploaded_db_path,
                    table_name,
                    business_context=dml_context,
                    dashboard_context=(
                        f"Dashboard/filter notes:\n{dashboard_notes or 'None provided.'}\n\n"
                        f"Manual chart replication context:\n{chart_replication_notes or 'None provided.'}"
                    ),
                )
                result = analyst.run(prompt, chat_history=history_for_agent, visual_context=visual_context)
            except LangChainAgentError as exc:
                st.error(str(exc))
                st.session_state.chat_messages.append({"role": "assistant", "content": str(exc)})
                st.stop()
            except Exception as exc:
                st.error("The LangChain agentic task failed.")
                st.exception(exc)
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": "The LangChain agentic task failed."}
                )
                st.stop()

        st.markdown(result["answer"])
        with st.expander("Analysis details", expanded=True):
            render_result_details(result, uploaded_db_path, table_name)

    st.session_state.chat_messages.append(
        {
            "role": "assistant",
            "content": result["answer"],
            "result": result,
        }
    )
    st.rerun()
