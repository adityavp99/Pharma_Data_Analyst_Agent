from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import sqlite3
from typing import Any

import numpy as np
import pandas as pd

from config import AGENT_ENABLE_PYTHON_TOOL, AGENT_MAX_SQL_ROWS, AGENT_RECURSION_LIMIT
from langchain_agentic.charting import summarize_chart_options, validate_chart_plan
from langchain_agentic.llm_factory import LangChainAgentError, build_chat_model
from tools.schema_tool import describe_table, get_schema_text, get_table_row_counts
from tools.sql_tool import run_readonly_sql


SYSTEM_PROMPT = """
You are a fully agentic data analyst for an uploaded CSV-backed SQLite database.

You must reason step by step and decide which tools to use. The user only gives a question.
You can inspect the dataset, run SQL, run pandas-based analysis, and propose a chart.

Operating rules:
- Use tools before answering factual questions about the data.
- Do not invent numbers. Numbers must come from tool results.
- Prefer SQL for filtering, grouping, joining, counting, totals, averages, and table previews.
- Treat columns such as year_month, YYYYMM, YYYY-MM, month, date, quarter, or year as time dimensions.
  Do not sum, average, or use time dimensions as y-axis measures.
- Use Python when the task needs statistical analysis, custom calculations, correlation, trend logic,
  reshaping, or dataframe exploration that is awkward in SQL.
- If the user asks what the CSV contains, inspect the dataset and summarize columns, row count,
  sample values, likely meaning, and good follow-up question ideas.
- If a visual would help, use inspect_chart_options first, then call propose_chart with columns that exist
  in the latest SQL result or uploaded dataframe.
- If propose_chart returns valid=false, repair the chart choice by aggregating/filtering data or choosing
  more appropriate columns/chart type before answering.
- Do not loop indefinitely on chart repairs. If a chart still cannot be made after two repair attempts,
  answer with the best table/evidence and clearly state why no chart was rendered.
- Prefer charting aggregated result data over raw uploaded data when the raw data is too granular.
- If the data is insufficient, say what is missing.
- Keep answers business-friendly and concise, but include enough evidence to be trusted.
- For generated charts, explain why that chart type and axis choice make sense.
- This is a local prototype. Do not provide medical, legal, regulatory, or treatment advice.
"""


def _safe_json(value: Any) -> str:
    def default(obj: Any) -> Any:
        if isinstance(obj, (pd.Timestamp, np.datetime64)):
            return str(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.DataFrame):
            return obj.head(100).to_dict("records")
        if isinstance(obj, pd.Series):
            return obj.to_dict()
        return str(obj)

    return json.dumps(value, default=default, indent=2)


def _read_table(db_path: str | Path, table_name: str, row_limit: int = 10000) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as conn:
        return pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT ?', conn, params=(row_limit,))


def _profile_frame(frame: pd.DataFrame) -> dict[str, Any]:
    columns: list[dict[str, Any]] = []
    for column in frame.columns:
        series = frame[column]
        column_profile: dict[str, Any] = {
            "name": column,
            "dtype": str(series.dtype),
            "non_null_count": int(series.notna().sum()),
            "null_count": int(series.isna().sum()),
            "unique_count": int(series.nunique(dropna=True)),
            "sample_values": series.dropna().astype(str).head(5).tolist(),
        }
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            column_profile["numeric_summary"] = {
                "min": float(numeric.min()),
                "max": float(numeric.max()),
                "mean": float(numeric.mean()),
            }
        columns.append(column_profile)
    return {
        "rows_loaded_for_profile": len(frame),
        "columns": columns,
    }


def _limited_observation(result: dict[str, Any], row_limit: int = 50) -> dict[str, Any]:
    if "error" in result:
        return result
    rows = result.get("rows", [])
    return {
        "columns": result.get("columns", []),
        "rows": rows[:row_limit],
        "row_count_returned_to_agent": min(len(rows), row_limit),
        "total_rows_returned_by_sql_tool": result.get("row_count", 0),
        "truncated_by_sql_tool": result.get("truncated", False),
        "sql_executed": result.get("sql_executed", ""),
    }


def _message_to_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _frame_from_sql_result(result: dict[str, Any] | None) -> pd.DataFrame | None:
    if not result or result.get("error"):
        return None
    return pd.DataFrame(result.get("rows", []), columns=result.get("columns", []))


class AgenticCSVAnalyst:
    def __init__(self, db_path: str | Path, table_name: str):
        self.db_path = Path(db_path)
        self.table_name = table_name
        self.frame = _read_table(self.db_path, self.table_name)
        self.state: dict[str, Any] = {
            "sql_queries": [],
            "python_runs": [],
            "chart_plan": None,
            "chart_validation": None,
            "last_sql_result": None,
            "last_python_result": None,
        }

    def _build_tools(self):
        try:
            from langchain_core.tools import tool
        except ImportError as exc:
            raise LangChainAgentError(
                "LangChain dependencies are not installed. Run `pip install -r requirements.txt`."
            ) from exc

        db_path = str(self.db_path)
        table_name = self.table_name
        frame = self.frame
        state = self.state

        @tool
        def inspect_dataset() -> str:
            """Inspect uploaded CSV schema, row counts, sample rows, and column-level profile."""
            details = describe_table(table_name, db_path, sample_rows=8)
            return _safe_json(
                {
                    "row_counts": get_table_row_counts(db_path),
                    "schema_text": get_schema_text(db_path),
                    "sample_rows": details["sample_rows"],
                    "profile": _profile_frame(frame),
                    "chart_options": summarize_chart_options(frame),
                }
            )

        @tool
        def query_dataset_sql(sql: str) -> str:
            """Run one read-only SQLite SELECT or WITH query against the uploaded CSV table."""
            result = run_readonly_sql(sql, db_path, max_rows=AGENT_MAX_SQL_ROWS)
            state["sql_queries"].append(sql)
            state["last_sql_result"] = result
            return _safe_json(_limited_observation(result))

        @tool
        def run_python_analysis(code: str) -> str:
            """Run local pandas analysis code against dataframe df and store answer in variable result."""
            if not AGENT_ENABLE_PYTHON_TOOL:
                return _safe_json({"error": "Python analysis tool is disabled."})

            stdout = StringIO()
            local_vars: dict[str, Any] = {
                "df": frame.copy(),
                "pd": pd,
                "np": np,
                "result": None,
            }
            allowed_builtins = {
                "abs": abs,
                "bool": bool,
                "dict": dict,
                "float": float,
                "int": int,
                "len": len,
                "list": list,
                "max": max,
                "min": min,
                "print": print,
                "range": range,
                "round": round,
                "set": set,
                "sorted": sorted,
                "str": str,
                "sum": sum,
                "tuple": tuple,
            }
            try:
                with redirect_stdout(stdout):
                    exec(
                        code,
                        {"__builtins__": allowed_builtins, "pd": pd, "np": np},
                        local_vars,
                    )
                payload = {
                    "printed_output": stdout.getvalue().strip(),
                    "result": local_vars.get("result"),
                }
            except Exception as exc:
                payload = {"error": str(exc), "printed_output": stdout.getvalue().strip()}

            state["python_runs"].append(code)
            state["last_python_result"] = payload
            return _safe_json(payload)

        @tool
        def inspect_chart_options(data_source: str = "latest_sql_result") -> str:
            """Inspect available columns and chart suitability for latest_sql_result or uploaded_dataframe."""
            source_frame = None
            if data_source == "latest_sql_result":
                source_frame = _frame_from_sql_result(state.get("last_sql_result"))
            if source_frame is None:
                source_frame = frame
                data_source = "uploaded_dataframe"
            return _safe_json(
                {
                    "data_source": data_source,
                    **summarize_chart_options(source_frame),
                }
            )

        @tool
        def propose_chart(
            chart_type: str,
            x_col: str,
            y_col: str,
            group_by: str | None = None,
            title: str | None = None,
            data_source: str = "latest_sql_result",
        ) -> str:
            """Validate and propose a chart. If valid=false, revise the chart before final answer."""
            source_frame = None
            if data_source == "latest_sql_result":
                source_frame = _frame_from_sql_result(state.get("last_sql_result"))
            if source_frame is None:
                source_frame = frame
                data_source = "uploaded_dataframe"
            plan = {
                "chart_type": str(chart_type).lower(),
                "x_col": x_col,
                "y_col": y_col,
                "group_by": group_by or None,
                "title": title or "Agent-generated chart",
                "data_source": data_source,
            }
            validation = validate_chart_plan(source_frame, plan)
            state["chart_validation"] = validation
            if validation["valid"]:
                state["chart_plan"] = plan
            else:
                state["chart_plan"] = None
            return _safe_json(validation)

        return [inspect_dataset, query_dataset_sql, run_python_analysis, inspect_chart_options, propose_chart]

    def run(self, question: str, chat_history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        try:
            from langchain.agents import create_agent
        except ImportError as exc:
            raise LangChainAgentError(
                "LangChain is not installed. Run `pip install -r requirements.txt`."
            ) from exc

        llm = build_chat_model()
        tools = self._build_tools()
        agent = create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)
        messages = [
            {"role": message["role"], "content": message["content"]}
            for message in (chat_history or [])[-8:]
            if message.get("role") in {"user", "assistant"} and message.get("content")
        ]
        messages.append({"role": "user", "content": question})
        response = agent.invoke(
            {"messages": messages},
            config={"recursion_limit": max(AGENT_RECURSION_LIMIT, 20)},
        )
        response_messages = response.get("messages", [])
        final_answer = _message_to_text(response_messages[-1]) if response_messages else ""
        return {
            "answer": final_answer,
            "messages": response_messages,
            "tool_trace": self._format_trace(response_messages),
            "chart_plan": self.state.get("chart_plan"),
            "chart_validation": self.state.get("chart_validation"),
            "last_sql_result": self.state.get("last_sql_result"),
            "last_python_result": self.state.get("last_python_result"),
            "sql_queries": self.state.get("sql_queries", []),
            "python_runs": self.state.get("python_runs", []),
        }

    @staticmethod
    def _format_trace(messages: list[Any]) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        for message in messages:
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                for call in tool_calls:
                    trace.append(
                        {
                            "type": "tool_call",
                            "tool": call.get("name"),
                            "arguments": call.get("args"),
                        }
                    )
            if message.__class__.__name__ == "ToolMessage":
                trace.append(
                    {
                        "type": "tool_result",
                        "tool": getattr(message, "name", ""),
                        "content_preview": _message_to_text(message)[:2000],
                    }
                )
        return trace
