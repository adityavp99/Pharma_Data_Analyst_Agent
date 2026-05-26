from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re


@dataclass(frozen=True)
class Dimension:
    name: str
    expression: str
    label: str


DIMENSIONS = {
    "trial": Dimension("trial", "t.trial_id", "trial_id"),
    "drug": Dimension("drug", "COALESCE(t.drug_name, ds.drug_name)", "drug_name"),
    "country": Dimension("country", "COALESCE(s.country, t.country, ds.country)", "country"),
    "therapeutic_area": Dimension("therapeutic_area", "t.therapeutic_area", "therapeutic_area"),
    "test": Dimension("test", "lr.test_name", "test_name"),
    "month": Dimension("month", "ds.month", "month"),
    "channel": Dimension("channel", "ds.channel", "channel"),
    "region": Dimension("region", "ds.region", "region"),
    "treatment_arm": Dimension("treatment_arm", "p.treatment_arm", "treatment_arm"),
}


METRIC_ALIASES = {
    "enrollment_rate": ["enrollment rate", "enrolled versus target"],
    "enrollment_gap": ["enrollment gap", "under enrolled", "under-enrolled", "shortfall"],
    "serious_ae_count": ["serious adverse event", "serious ae", "sae"],
    "related_ae_count": ["related adverse event", "related ae"],
    "ae_rate_per_patient": ["ae rate", "adverse event rate", "adverse events per patient"],
    "out_of_range_lab_rate": ["out-of-range lab", "out of range lab", "abnormal lab"],
    "net_sales": ["net sales", "revenue"],
    "units_sold": ["units sold", "sold the most", "most sold", "sold"],
    "net_sales_per_unit": ["net sales per unit", "price per unit"],
}


def infer_metric_name(question: str) -> str | None:
    normalized = question.lower()
    for metric_name, aliases in METRIC_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return metric_name
    return None


def infer_dimensions(question: str, metric_name: str) -> list[str]:
    q = question.lower()
    dimensions: list[str] = []
    phrase_to_dimension = [
        ("by treatment arm", "treatment_arm"),
        ("by therapeutic area", "therapeutic_area"),
        ("by country", "country"),
        ("by region", "region"),
        ("by channel", "channel"),
        ("by month", "month"),
        ("by test", "test"),
        ("by lab", "test"),
        ("by drug", "drug"),
        ("by trial", "trial"),
    ]
    for phrase, dimension in phrase_to_dimension:
        if phrase in q and dimension not in dimensions:
            dimensions.append(dimension)

    if dimensions:
        return dimensions

    if metric_name in {"enrollment_rate", "enrollment_gap", "serious_ae_count", "ae_rate_per_patient"}:
        return ["trial"]
    if metric_name == "out_of_range_lab_rate":
        return ["test"]
    if metric_name in {"net_sales", "units_sold", "net_sales_per_unit"}:
        return ["drug"]
    return ["trial"]


def infer_limit(question: str, default: int = 10) -> int:
    match = re.search(r"\btop\s+(\d+)|\bbottom\s+(\d+)|\blimit\s+(\d+)", question.lower())
    if not match:
        return default
    return min(max(int(next(group for group in match.groups() if group)), 1), 200)


def _select_group_by(dimensions: list[str]) -> tuple[str, str]:
    selected = [DIMENSIONS[dimension] for dimension in dimensions]
    select_sql = ",\n  ".join(f"{dimension.expression} AS {dimension.label}" for dimension in selected)
    group_sql = ", ".join(dimension.expression for dimension in selected)
    return select_sql, group_sql


def _order_direction(question: str) -> str:
    q = question.lower()
    if any(term in q for term in ["lowest", "least", "bottom", "smallest"]):
        return "ASC"
    return "DESC"


def _sales_select_group_by(dimensions: list[str]) -> tuple[str, str]:
    sales_dimensions = {
        "drug": ("ds.drug_name", "drug_name"),
        "country": ("ds.country", "country"),
        "region": ("ds.region", "region"),
        "month": ("ds.month", "month"),
        "channel": ("ds.channel", "channel"),
    }
    selected = [sales_dimensions.get(dimension) for dimension in dimensions]
    selected = [dimension for dimension in selected if dimension is not None]
    if not selected:
        selected = [sales_dimensions["drug"]]
    select_sql = ",\n  ".join(f"{expression} AS {label}" for expression, label in selected)
    group_sql = ", ".join(expression for expression, _ in selected)
    return select_sql, group_sql


def build_metric_sql(metric_name: str, question: str, dimensions: list[str] | None = None) -> dict[str, Any]:
    dimensions = dimensions or infer_dimensions(question, metric_name)
    limit = infer_limit(question)
    direction = _order_direction(question)
    select_dims, group_by = _select_group_by(dimensions)

    if metric_name == "enrollment_rate":
        return {
            "sql": f"""
SELECT
  {select_dims},
  SUM(s.enrolled_patients) AS enrolled_patients,
  SUM(s.enrollment_target) AS enrollment_target,
  ROUND(100.0 * SUM(s.enrolled_patients) / NULLIF(SUM(s.enrollment_target), 0), 2) AS enrollment_rate_pct
FROM sites s
JOIN trials t ON t.trial_id = s.trial_id
GROUP BY {group_by}
ORDER BY enrollment_rate_pct {direction}
LIMIT {limit}
""".strip(),
            "explanation": "Enrollment rate uses SUM(enrolled_patients) divided by SUM(enrollment_target).",
            "assumptions": ["Enrollment metrics use site-level targets and enrolled counts."],
            "python": None,
            "planner_source": "metric_sql_builder",
        }

    if metric_name == "enrollment_gap":
        return {
            "sql": f"""
SELECT
  {select_dims},
  SUM(s.enrollment_target) AS enrollment_target,
  SUM(s.enrolled_patients) AS enrolled_patients,
  SUM(s.enrollment_target) - SUM(s.enrolled_patients) AS enrollment_gap
FROM sites s
JOIN trials t ON t.trial_id = s.trial_id
GROUP BY {group_by}
ORDER BY enrollment_gap {direction}
LIMIT {limit}
""".strip(),
            "explanation": "Enrollment gap is target minus enrolled patients.",
            "assumptions": ["Positive gaps indicate under-enrollment."],
            "python": None,
            "planner_source": "metric_sql_builder",
        }

    if metric_name in {"serious_ae_count", "related_ae_count"}:
        condition = "ae.seriousness = 'Serious'" if metric_name == "serious_ae_count" else "ae.related_to_drug = 1"
        metric_col = metric_name
        return {
            "sql": f"""
SELECT
  {select_dims},
  COUNT(ae.ae_id) AS {metric_col},
  COUNT(DISTINCT ae.patient_id) AS patients_with_events
FROM adverse_events ae
JOIN trials t ON t.trial_id = ae.trial_id
LEFT JOIN patients p ON p.patient_id = ae.patient_id
WHERE {condition}
GROUP BY {group_by}
ORDER BY {metric_col} {direction}
LIMIT {limit}
""".strip(),
            "explanation": f"{metric_col} is a descriptive adverse event count using the semantic-layer definition.",
            "assumptions": ["Adverse event outputs are descriptive only and do not imply causality."],
            "python": None,
            "planner_source": "metric_sql_builder",
        }

    if metric_name == "ae_rate_per_patient":
        return {
            "sql": f"""
SELECT
  {select_dims},
  COUNT(ae.ae_id) AS adverse_event_count,
  COUNT(DISTINCT p.patient_id) AS patient_count,
  ROUND(1.0 * COUNT(ae.ae_id) / NULLIF(COUNT(DISTINCT p.patient_id), 0), 3) AS ae_rate_per_patient
FROM patients p
JOIN trials t ON t.trial_id = p.trial_id
LEFT JOIN adverse_events ae ON ae.patient_id = p.patient_id
GROUP BY {group_by}
ORDER BY ae_rate_per_patient {direction}
LIMIT {limit}
""".strip(),
            "explanation": "AE rate per patient is adverse event count divided by distinct synthetic patients.",
            "assumptions": ["Observation windows are not normalized in this MVP."],
            "python": None,
            "planner_source": "metric_sql_builder",
        }

    if metric_name == "out_of_range_lab_rate":
        return {
            "sql": f"""
SELECT
  {select_dims},
  COUNT(*) AS lab_result_count,
  SUM(CASE WHEN lr.result_value < lr.normal_low OR lr.result_value > lr.normal_high THEN 1 ELSE 0 END) AS out_of_range_count,
  ROUND(100.0 * SUM(CASE WHEN lr.result_value < lr.normal_low OR lr.result_value > lr.normal_high THEN 1 ELSE 0 END) / COUNT(*), 2) AS out_of_range_rate_pct
FROM lab_results lr
JOIN trials t ON t.trial_id = lr.trial_id
LEFT JOIN patients p ON p.patient_id = lr.patient_id
GROUP BY {group_by}
ORDER BY out_of_range_rate_pct {direction}
LIMIT {limit}
""".strip(),
            "explanation": "Out-of-range lab rate is the share of results outside normal_low/normal_high.",
            "assumptions": ["Lab reference ranges are synthetic and simplified."],
            "python": None,
            "planner_source": "metric_sql_builder",
        }

    if metric_name in {"net_sales", "units_sold", "net_sales_per_unit"}:
        sales_select_dims, sales_group_by = _sales_select_group_by(dimensions)
        metric_expr = {
            "net_sales": "ROUND(SUM(ds.net_sales), 2)",
            "units_sold": "SUM(ds.units_sold)",
            "net_sales_per_unit": "ROUND(SUM(ds.net_sales) / NULLIF(SUM(ds.units_sold), 0), 2)",
        }[metric_name]
        metric_col = metric_name
        return {
            "sql": f"""
SELECT
  {sales_select_dims},
  SUM(ds.units_sold) AS units_sold,
  ROUND(SUM(ds.net_sales), 2) AS net_sales,
  ROUND(SUM(ds.net_sales) / NULLIF(SUM(ds.units_sold), 0), 2) AS net_sales_per_unit,
  {metric_expr} AS metric_value
FROM drug_sales ds
GROUP BY {sales_group_by}
ORDER BY metric_value {direction}
LIMIT {limit}
""".strip(),
            "explanation": f"{metric_name} is calculated from the drug_sales table using the semantic-layer definition.",
            "assumptions": ["Using all available months, countries, and channels unless a question specifies filters."],
            "python": None,
            "planner_source": "metric_sql_builder",
        }

    raise ValueError(f"Unsupported metric SQL builder: {metric_name}")


def build_metric_plan_from_question(question: str) -> dict[str, Any] | None:
    metric_name = infer_metric_name(question)
    if not metric_name:
        return None
    return build_metric_sql(metric_name, question)
