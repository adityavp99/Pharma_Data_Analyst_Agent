from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _to_frame(data: dict[str, Any]) -> pd.DataFrame:
    if "error" in data:
        raise ValueError(f"Cannot analyze SQL error result: {data['error']}")
    return pd.DataFrame(data.get("rows", []), columns=data.get("columns", []))


def _jsonify(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def calculate_correlation(data: dict[str, Any], x_col: str, y_col: str) -> dict[str, Any]:
    frame = _to_frame(data)
    correlation = frame[x_col].astype(float).corr(frame[y_col].astype(float))
    return _jsonify({"x_col": x_col, "y_col": y_col, "correlation": correlation, "rows_used": len(frame)})


def calculate_summary_statistics(
    data: dict[str, Any], group_by: str | list[str] | None = None, value_col: str | None = None
) -> dict[str, Any]:
    frame = _to_frame(data)
    if value_col is None:
        numeric_cols = frame.select_dtypes(include=["number"]).columns.tolist()
        if not numeric_cols:
            numeric_cols = [col for col in frame.columns if pd.to_numeric(frame[col], errors="coerce").notna().any()]
        value_col = numeric_cols[0] if numeric_cols else frame.columns[0]
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    if group_by:
        grouped = frame.groupby(group_by)[value_col].agg(["count", "mean", "median", "std", "min", "max"]).reset_index()
        return _jsonify({"statistics": grouped.to_dict("records"), "value_col": value_col, "group_by": group_by})
    stats = frame[value_col].agg(["count", "mean", "median", "std", "min", "max"]).to_dict()
    return _jsonify({"statistics": stats, "value_col": value_col})


def calculate_trend(
    data: dict[str, Any], date_col: str, value_col: str, group_by: str | list[str] | None = None
) -> dict[str, Any]:
    frame = _to_frame(data)
    frame[date_col] = pd.to_datetime(frame[date_col])
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame["_period"] = frame[date_col].dt.to_period("M").dt.to_timestamp()
    group_cols = ([group_by] if isinstance(group_by, str) else group_by or []) + ["_period"]
    trend = frame.groupby(group_cols, dropna=False)[value_col].sum().reset_index()
    trend["_period"] = trend["_period"].dt.strftime("%Y-%m-%d")
    return _jsonify({"trend": trend.to_dict("records"), "date_col": date_col, "value_col": value_col, "group_by": group_by})


def calculate_percentage_change(
    data: dict[str, Any], date_col: str, value_col: str, group_by: str | list[str] | None = None
) -> dict[str, Any]:
    frame = _to_frame(data)
    frame[date_col] = pd.to_datetime(frame[date_col])
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    group_cols = [group_by] if isinstance(group_by, str) else group_by or []
    sort_cols = group_cols + [date_col]
    frame = frame.sort_values(sort_cols)
    if group_cols:
        frame["percentage_change"] = frame.groupby(group_cols)[value_col].pct_change() * 100
    else:
        frame["percentage_change"] = frame[value_col].pct_change() * 100
    return _jsonify({"percentage_change": frame.to_dict("records"), "value_col": value_col, "date_col": date_col, "group_by": group_by})


def detect_simple_outliers(data: dict[str, Any], value_col: str, method: str = "iqr") -> dict[str, Any]:
    if method != "iqr":
        raise ValueError("Only the iqr outlier method is supported in the MVP.")
    frame = _to_frame(data)
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    q1 = frame[value_col].quantile(0.25)
    q3 = frame[value_col].quantile(0.75)
    iqr = q3 - q1
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    outliers = frame[(frame[value_col] < low) | (frame[value_col] > high)]
    return _jsonify({"method": method, "low_threshold": low, "high_threshold": high, "outliers": outliers.to_dict("records")})


def create_chart_data(
    data: dict[str, Any], chart_type: str, x_col: str, y_col: str, group_by: str | list[str] | None = None
) -> dict[str, Any]:
    frame = _to_frame(data)
    columns = [x_col, y_col] + ([group_by] if isinstance(group_by, str) else group_by or [])
    chart_data = frame[columns].to_dict("records")
    return _jsonify({"chart_type": chart_type, "x_col": x_col, "y_col": y_col, "group_by": group_by, "data": chart_data})
