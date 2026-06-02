from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px


SUPPORTED_CHART_TYPES = {"bar", "line", "scatter", "area"}


def _is_datetime_like(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().astype(str).head(50)
    if sample.empty:
        return False
    dateish = sample.str.contains(r"\d{4}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}", regex=True)
    if dateish.mean() < 0.5:
        return False
    parsed = pd.to_datetime(series, errors="coerce")
    return bool(len(series) > 0 and parsed.notna().mean() >= 0.8)


def _column_role(series: pd.Series) -> str:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() >= 0.8:
        return "numeric"
    if _is_datetime_like(series):
        return "datetime"
    return "categorical"


def summarize_chart_options(frame: pd.DataFrame) -> dict[str, Any]:
    columns = []
    for column in frame.columns:
        series = frame[column]
        role = _column_role(series)
        item: dict[str, Any] = {
            "name": column,
            "role": role,
            "non_null_count": int(series.notna().sum()),
            "unique_count": int(series.nunique(dropna=True)),
        }
        if role == "numeric":
            numeric = pd.to_numeric(series, errors="coerce")
            item["min"] = float(numeric.min())
            item["max"] = float(numeric.max())
        columns.append(item)

    return {
        "row_count": len(frame),
        "columns": columns,
        "chart_guidance": [
            "Use line or area charts for time trends.",
            "Use bar charts for category comparisons, ideally with 20 or fewer x-axis categories.",
            "Use scatter charts for relationships between two numeric measures.",
            "Use a grouped color only when the grouping column has a small number of categories.",
            "If the data is too granular, run SQL or Python first to aggregate it to the chart grain.",
        ],
    }


def validate_chart_plan(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    chart_type = str(plan.get("chart_type", "")).lower()
    x_col = plan.get("x_col")
    y_col = plan.get("y_col")
    group_by = plan.get("group_by")

    if frame.empty:
        issues.append("No rows are available for charting.")
    if chart_type not in SUPPORTED_CHART_TYPES:
        issues.append(f"Unsupported chart_type `{chart_type}`. Use one of {sorted(SUPPORTED_CHART_TYPES)}.")
    if x_col not in frame.columns:
        issues.append(f"x_col `{x_col}` is not present in the chart data.")
    if y_col not in frame.columns:
        issues.append(f"y_col `{y_col}` is not present in the chart data.")
    if group_by and group_by not in frame.columns:
        issues.append(f"group_by `{group_by}` is not present in the chart data.")
    if issues:
        return {"valid": False, "issues": issues, "warnings": warnings, "plan": plan}

    y_numeric = pd.to_numeric(frame[y_col], errors="coerce")
    if y_numeric.notna().mean() < 0.8:
        issues.append(f"y_col `{y_col}` is not mostly numeric, so it cannot be used as a quantitative y-axis.")

    x_role = _column_role(frame[x_col])
    y_role = _column_role(frame[y_col])
    x_unique = int(frame[x_col].nunique(dropna=True))

    if chart_type in {"line", "area"} and x_role not in {"datetime", "numeric"}:
        issues.append(
            f"{chart_type} charts need a time-like or ordered numeric x-axis; `{x_col}` looks {x_role}."
        )
    if chart_type == "scatter" and x_role != "numeric":
        issues.append(f"scatter charts need a numeric x-axis; `{x_col}` looks {x_role}.")
    if chart_type == "bar" and x_unique > 30:
        warnings.append(
            f"`{x_col}` has {x_unique} distinct values. Consider aggregating/filtering to avoid a crowded bar chart."
        )
    if group_by:
        group_unique = int(frame[group_by].nunique(dropna=True))
        if group_unique > 12:
            warnings.append(
                f"`{group_by}` has {group_unique} groups. Consider filtering or using a smaller grouping column."
            )
    if len(frame) > 1000:
        warnings.append("The chart data has more than 1,000 rows. Consider aggregating before charting.")

    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "plan": plan,
        "roles": {
            "x_col": x_role,
            "y_col": y_role,
            "group_by": _column_role(frame[group_by]) if group_by else None,
        },
    }


def prepare_chart_frame(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    prepared = frame.copy()
    x_col = plan["x_col"]
    y_col = plan["y_col"]
    prepared[y_col] = pd.to_numeric(prepared[y_col], errors="coerce")
    if _is_datetime_like(prepared[x_col]):
        prepared[x_col] = pd.to_datetime(prepared[x_col], errors="coerce")
    return prepared.dropna(subset=[x_col, y_col])


def build_plotly_chart(frame: pd.DataFrame, plan: dict[str, Any]):
    chart_type = str(plan.get("chart_type", "bar")).lower()
    x_col = plan["x_col"]
    y_col = plan["y_col"]
    group_by = plan.get("group_by")
    title = plan.get("title") or "Agent chart"
    prepared = prepare_chart_frame(frame, plan)

    common = {
        "data_frame": prepared,
        "x": x_col,
        "y": y_col,
        "color": group_by if group_by in prepared.columns else None,
        "title": title,
    }
    if chart_type == "line":
        fig = px.line(**common, markers=True)
    elif chart_type == "scatter":
        fig = px.scatter(**common)
    elif chart_type == "area":
        fig = px.area(**common)
    else:
        fig = px.bar(**common)

    fig.update_layout(
        margin={"l": 20, "r": 20, "t": 52, "b": 20},
        legend_title_text=str(group_by).replace("_", " ").title() if group_by else None,
        xaxis_title=str(x_col).replace("_", " ").title(),
        yaxis_title=str(y_col).replace("_", " ").title(),
    )
    return fig
