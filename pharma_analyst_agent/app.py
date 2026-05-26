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

from agent.orchestrator import answer_question
from agent.response_formatter import summarize_python_result
from config import DB_PATH
from tools.schema_tool import get_table_row_counts


QUESTION_TEMPLATES = {
    "Semantic only": [
        "What does enrollment rate mean?",
        "Define serious adverse event.",
        "What is an out-of-range lab result?",
    ],
    "SQL only": [
        "Which drug was sold the most?",
        "Which drug had the highest net sales?",
        "Which trials have the highest enrollment rate?",
        "Show the top 10 trials by serious adverse event count.",
        "What is the out-of-range lab rate by test?",
    ],
    "Semantic + SQL": [
        "Using the enrollment rate definition, which trials have the highest enrollment rate?",
        "Using the serious adverse event definition, show the top 10 trials by serious adverse event count.",
        "Using the net sales definition, which drug had the highest net sales?",
    ],
    "SQL + Python": [
        "Show monthly net sales trend by drug.",
        "Calculate percentage change in monthly net sales by drug.",
        "Find outliers in monthly net sales.",
        "What is the correlation between enrolled patients and adverse event count?",
    ],
    "Semantic + SQL + Python": [
        "Using the net sales definition, show monthly net sales trend by drug.",
        "Using the adverse event definition, what is the correlation between enrolled patients and adverse event count?",
        "Using the net sales definition, find outliers in monthly net sales.",
    ],
    "Safety refusal": [
        "Which drug should this patient take?",
        "Did the drug cause these serious adverse events?",
    ],
}


TABLE_CATALOG = [
    {
        "table": "trials",
        "what_it_contains": "One row per synthetic clinical trial.",
        "use_it_for": "Trial portfolio summaries, phase/status breakdowns, therapeutic area analysis, trial-to-drug mapping.",
        "key_columns": "trial_id, phase, therapeutic_area, drug_name, indication, status, country, planned_enrollment",
        "example_questions": "How many trials are in each therapeutic area? Which trials are recruiting? Which drugs are studied in Oncology?",
    },
    {
        "table": "sites",
        "what_it_contains": "Synthetic trial sites and enrollment performance.",
        "use_it_for": "Enrollment rate, enrollment gap, country/site contribution, site-level performance.",
        "key_columns": "site_id, trial_id, country, investigator_name, enrollment_target, enrolled_patients",
        "example_questions": "Which trials have the highest enrollment gap? Which countries enrolled the most patients?",
    },
    {
        "table": "patients",
        "what_it_contains": "Synthetic participant records with coarse demographics only.",
        "use_it_for": "Aggregate patient counts by trial, site, age group, sex, baseline condition, or treatment arm.",
        "key_columns": "patient_id, trial_id, site_id, age_group, sex, baseline_condition, treatment_arm",
        "example_questions": "How many patients are in each treatment arm? What is the patient mix by age group?",
    },
    {
        "table": "adverse_events",
        "what_it_contains": "Synthetic adverse event records linked to synthetic patients and trials.",
        "use_it_for": "Descriptive AE counts, serious AE counts, related AE counts, AE rates per patient.",
        "key_columns": "ae_id, patient_id, trial_id, event_term, severity, seriousness, outcome, event_date, related_to_drug",
        "example_questions": "Which trials have the most serious adverse events? What are the most common AE terms?",
    },
    {
        "table": "lab_results",
        "what_it_contains": "Synthetic lab measurements with simplified normal ranges.",
        "use_it_for": "Out-of-range lab rates, lab summaries by test, abnormal lab monitoring.",
        "key_columns": "lab_id, patient_id, trial_id, test_name, result_value, unit, normal_low, normal_high, result_date",
        "example_questions": "Which lab test has the highest out-of-range rate? What are ALT summary statistics?",
    },
    {
        "table": "drug_sales",
        "what_it_contains": "Synthetic monthly commercial sales by drug, country, region, and channel.",
        "use_it_for": "Units sold, net sales, net sales per unit, country/region/channel sales trends.",
        "key_columns": "sale_id, drug_name, country, region, month, units_sold, net_sales, channel, currency",
        "example_questions": "Which drug sold the most? What is the monthly sales trend by drug? Which country has the highest net sales?",
    },
]


def _all_examples() -> list[str]:
    return [question for questions in QUESTION_TEMPLATES.values() for question in questions]


def _apply_template() -> None:
    st.session_state.question = st.session_state.selected_template


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
    base = alt.Chart(frame).encode(
        x=alt.X(f"{x_col}:{x_type}", title=x_col.replace("_", " ").title()),
        y=alt.Y(f"{y_col}:Q", title=y_col.replace("_", " ").title()),
        tooltip=[col for col in frame.columns if col in {x_col, y_col, group_by, "country", "region", "trial_id", "drug_name", "test_name"}],
    )
    if group_by and group_by in frame.columns:
        base = base.encode(color=alt.Color(f"{group_by}:N", title=group_by.replace("_", " ").title()))

    chart = base.mark_line(point=True) if chart_type == "line" else base.mark_bar()
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


st.set_page_config(page_title="Pharma Analyst Agent MVP", layout="wide")
st.title("Pharma Analyst Agent MVP")
st.caption("Ask business questions over synthetic pharma-style trial, safety, lab, and sales data.")

if not DB_PATH.exists():
    st.warning("Database not found. Run `python scripts/generate_synthetic_data.py` and `python scripts/load_sqlite.py` first.")
    st.stop()

with st.sidebar:
    st.subheader("Synthetic database")
    counts = get_table_row_counts(DB_PATH)
    st.dataframe(pd.DataFrame([{"table": key, "rows": value} for key, value in counts.items()]), hide_index=True)
    with st.expander("Data catalog", expanded=False):
        st.dataframe(pd.DataFrame(TABLE_CATALOG), hide_index=True, use_container_width=True)

if "question" not in st.session_state:
    st.session_state.question = _all_examples()[0]

template_group = st.selectbox("Question type", list(QUESTION_TEMPLATES))
st.selectbox(
    "Question template",
    QUESTION_TEMPLATES[template_group],
    key="selected_template",
    on_change=_apply_template,
)
st.button("Use selected template", on_click=_apply_template)

question = st.text_input("Ask an analytical question", key="question")

with st.expander("What data can I ask about?", expanded=False):
    st.dataframe(pd.DataFrame(TABLE_CATALOG), hide_index=True, use_container_width=True)

if st.button("Analyze", type="primary") and question:
    with st.spinner("Routing tools and analyzing synthetic data..."):
        result = answer_question(question, DB_PATH)

    if result.get("business_summary"):
        st.success(result["business_summary"])

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
        st.write("1. Route the question to semantic definitions, SQL, Python, or safe refusal.")
        st.write("2. Add business definitions from the semantic layer when useful.")
        st.write("3. Run only read-only SQL against the synthetic SQLite database.")
        st.write("4. Run controlled Python only for trends, percentage change, summaries, or outliers.")
        st.write("5. Show the evidence, SQL, assumptions, and limitations.")
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
