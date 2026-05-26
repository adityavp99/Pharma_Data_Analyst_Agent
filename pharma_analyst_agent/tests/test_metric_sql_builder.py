from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.metric_sql_builder import build_metric_plan_from_question, build_metric_sql, infer_dimensions, infer_metric_name
from tools.sql_tool import validate_sql


def test_infer_metric_name_for_sales_and_enrollment() -> None:
    assert infer_metric_name("Which drug was sold the most?") == "units_sold"
    assert infer_metric_name("Which trials have the highest enrollment rate?") == "enrollment_rate"


def test_infer_dimensions_from_question() -> None:
    assert infer_dimensions("Show net sales by country", "net_sales") == ["country"]
    assert infer_dimensions("Show out-of-range lab rate by test", "out_of_range_lab_rate") == ["test"]


def test_build_enrollment_rate_sql_is_readonly() -> None:
    plan = build_metric_sql("enrollment_rate", "Which trials have the highest enrollment rate?")
    validate_sql(plan["sql"])
    assert "SUM(s.enrolled_patients)" in plan["sql"]
    assert plan["planner_source"] == "metric_sql_builder"


def test_sales_builder_does_not_join_trials_for_drug_sales() -> None:
    plan = build_metric_plan_from_question("Which drug was sold the most?")
    assert plan is not None
    validate_sql(plan["sql"])
    assert "FROM drug_sales ds" in plan["sql"]
    assert "JOIN trials" not in plan["sql"]
    assert "SUM(ds.units_sold)" in plan["sql"]
