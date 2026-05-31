from __future__ import annotations

from typing import Any
import base64
import json
import re

from agent.llm_client import get_vision_client


SUPPORTED_CHART_TYPES = {"bar", "line", "scatter"}


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def infer_chart_plan_from_screenshot(
    image_bytes: bytes,
    available_columns: list[str],
    question: str = "",
) -> dict[str, Any] | None:
    client, model, provider = get_vision_client()
    if client is None:
        return None

    encoded = base64.b64encode(image_bytes).decode("utf-8")
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You inspect a dashboard/chart screenshot and map it to a chart plan "
                    "using only the provided dataframe columns. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"User question: {question}\n"
                            f"Available columns: {available_columns}\n\n"
                            "Return JSON:\n"
                            "{\n"
                            '  "chart_type": "bar|line|scatter",\n'
                            '  "x_col": "one available column",\n'
                            '  "y_col": "one available numeric column",\n'
                            '  "group_by": "optional available column or null",\n'
                            '  "title": "short title",\n'
                            '  "rationale": "brief explanation"\n'
                            "}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                ],
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    parsed = _extract_json(content)
    chart_type = parsed.get("chart_type")
    x_col = parsed.get("x_col")
    y_col = parsed.get("y_col")
    group_by = parsed.get("group_by")
    if chart_type not in SUPPORTED_CHART_TYPES:
        return None
    if x_col not in available_columns or y_col not in available_columns:
        return None
    if group_by not in available_columns:
        group_by = None
    return {
        "source": "sql_result",
        "chart_type": chart_type,
        "x_col": x_col,
        "y_col": y_col,
        "group_by": group_by,
        "title": parsed.get("title") or "Replicated chart",
        "rationale": parsed.get("rationale", ""),
        "planner_source": f"vision_{provider}",
    }
