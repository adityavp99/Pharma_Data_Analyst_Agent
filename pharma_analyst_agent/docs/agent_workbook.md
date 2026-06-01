# Pharma Analyst Agent Workbook

This workbook explains the current data analyst agent in enough depth to answer technical, product, architecture, and migration questions. It is written for internal learning and stakeholder conversations.

## 1. Executive Summary

We have built a local proof-of-concept data analyst agent for structured pharmaceutical-style data.

The agent can:

- Answer natural-language analytical questions.
- Decide whether the question needs semantic definitions, SQL, Python analysis, or a safety refusal.
- Use a semantic layer for metric definitions, glossary terms, entities, and approved joins.
- Build SQL using tested metric SQL builders for known metrics.
- Use OpenRouter/LLM planning for questions not covered by builders, if configured.
- Validate all SQL before execution.
- Execute SQLite queries in read-only mode.
- Run only controlled Python functions for analysis such as trends, percentage change, correlation, and outlier detection.
- Render an answer, table, chart, SQL source of truth, semantic context, and Python debug output in Streamlit.

The most important design principle is this:

The LLM is allowed to help plan or summarize, but it is not trusted as the source of truth. The source of truth is the database query result, the controlled Python result, and the semantic layer.

## 2. Current Architecture At A Glance

Current flow:

```text
User question
  -> Streamlit UI
  -> Router decides high-level tool needs
  -> Semantic context is retrieved if relevant
  -> SQL planner creates a plan
      -> Python-analysis template first
      -> metric SQL builder second
      -> optional OpenRouter LLM fallback third
      -> safe fallback query last
  -> SQL tool validates and executes read-only SQL
  -> Python tool optionally performs controlled analysis
  -> Chart recommender chooses chart type and axes
  -> Response formatter writes the final explanation
  -> Streamlit renders answer, chart, table, SQL, semantic context, Python output
```

Main files:

| File | Purpose |
|---|---|
| `app.py` | Streamlit frontend and visualization layer. |
| `agent/tool_router.py` | Decides whether a question needs SQL, Python, semantic context, or refusal. |
| `agent/sql_planner.py` | Main planning stack: Python templates, metric SQL builders, LLM fallback, safe fallback. |
| `agent/orchestrator.py` | Coordinates routing, planning, SQL execution, Python execution, chart recommendation, and final answer formatting. |
| `agent/context_builder.py` | Builds compact context for the LLM: relevant semantic context, schema, and join paths. |
| `agent/llm_summary.py` | Optional OpenRouter summarizer for nontechnical business phrasing. |
| `agent/response_formatter.py` | Turns results into readable final answers. |
| `tools/sql_tool.py` | Read-only SQL validation and execution. |
| `tools/python_tool.py` | Controlled pandas/numpy analysis functions. |
| `tools/metric_sql_builder.py` | Unit-tested metric SQL generation for known metrics. |
| `tools/schema_tool.py` | Database schema inspection. |
| `tools/semantic_tool.py` | Loads/searches the semantic layer. |
| `semantic_layer/*.yaml` | Business definitions, ontology, glossary, and approved join paths. |
| `scripts/generate_synthetic_data.py` | Creates synthetic pharma-style CSVs. |
| `scripts/load_sqlite.py` | Loads CSVs into SQLite. |
| `tests/` | Regression tests for safety, semantic layer, metric SQL builders, and sample questions. |

## 3. Where The LLM Is Used

There are currently two possible LLM uses, both through OpenRouter-compatible OpenAI client calls.

### 3.1 LLM SQL Planner

File:

`agent/sql_planner.py`

Function:

`_llm_plan(user_question, db_path)`

The LLM planner is used only when:

1. `ENABLE_LLM_PLANNER=true`
2. `OPENROUTER_API_KEY` is present
3. The question was not handled by a Python-analysis template
4. The question was not handled by a known metric SQL builder

Planner order in `plan_query()`:

```python
python_plan = _python_first_plan(user_question)
if python_plan:
    return python_plan

metric_plan = build_metric_plan_from_question(user_question)
if metric_plan:
    return metric_plan

llm_plan = _llm_plan(user_question, db_path)
if llm_plan:
    return llm_plan

return _fallback_portfolio_plan()
```

This means the LLM is a fallback planner, not the first thing we call.

Why this matters:

- Known metrics should be consistent and unit-tested.
- Trend/correlation/outlier questions need controlled Python workflows.
- The LLM is helpful for flexible long-tail questions, but every LLM SQL query is still validated before execution.

### 3.2 LLM Business Summary

File:

`agent/llm_summary.py`

Function:

`summarize_for_business_user(...)`

This is separate from SQL planning. It rewrites an already-computed answer into a more business-friendly summary.

It is enabled only when:

```bash
AI_SUMMARY_PROVIDER=openrouter
OPENROUTER_API_KEY=...
```

Important:

The summarizer receives the SQL result and deterministic answer. It is instructed not to invent numbers. It should not be treated as the source of truth.

## 4. How The Agent Decides What To Do

### 4.1 Router

File:

`agent/tool_router.py`

The router classifies the user question into:

- `semantic_only`
- `sql_only`
- `sql_python`
- `semantic_sql`
- `semantic_sql_python`
- `refusal`

It looks for keywords and semantic matches.

Examples:

| Question | Expected route |
|---|---|
| `What does enrollment rate mean?` | semantic only |
| `Which drug was sold the most?` | semantic + SQL |
| `Show monthly net sales trend by drug.` | semantic + SQL + Python |
| `What is the correlation between enrolled patients and adverse event count?` | semantic + SQL + Python |
| `Which drug should this patient take?` | refusal |

The router does not write SQL. It only decides which broad capabilities are needed.

### 4.2 SQL Planner

File:

`agent/sql_planner.py`

The SQL planner writes or selects the SQL plan.

It has four layers:

1. Python-analysis templates
2. Metric SQL builders
3. Optional OpenRouter LLM SQL generation
4. Safe fallback query

This is the most important file for understanding how SQL is created.

## 5. Predetermined SQL Statements

There are two kinds of predetermined SQL in the current system.

### 5.1 Python-Analysis Templates

File:

`agent/sql_planner.py`

Function:

`_python_first_plan(user_question)`

These are used when a question requires post-query analysis in Python.

Current templates:

#### Monthly Sales Trend

Triggered by words like:

- trend
- growth
- percentage change
- sales
- net sales

SQL:

```sql
SELECT
  drug_name,
  month,
  SUM(net_sales) AS net_sales
FROM drug_sales
GROUP BY drug_name, month
ORDER BY drug_name, month
LIMIT 1000
```

Then Python runs:

- `calculate_trend(...)`, or
- `calculate_percentage_change(...)`

#### Correlation

Triggered by:

- correlation

SQL prepares trial-level enrollment and adverse event counts:

```sql
WITH site_agg AS (
  SELECT
    trial_id,
    SUM(enrollment_target) AS enrollment_target,
    SUM(enrolled_patients) AS enrolled_patients
  FROM sites
  GROUP BY trial_id
),
ae_agg AS (
  SELECT
    trial_id,
    COUNT(ae_id) AS adverse_event_count
  FROM adverse_events
  GROUP BY trial_id
)
SELECT
  s.trial_id,
  s.enrollment_target,
  s.enrolled_patients,
  COALESCE(a.adverse_event_count, 0) AS adverse_event_count
FROM site_agg s
LEFT JOIN ae_agg a ON a.trial_id = s.trial_id
```

Then Python runs:

`calculate_correlation(x_col="enrolled_patients", y_col="adverse_event_count")`

#### Outlier Detection

Triggered by:

- outlier
- outliers

SQL:

```sql
SELECT
  drug_name,
  country,
  month,
  SUM(net_sales) AS net_sales
FROM drug_sales
GROUP BY drug_name, country, month
ORDER BY net_sales DESC
LIMIT 2000
```

Then Python runs:

`detect_simple_outliers(value_col="net_sales", method="iqr")`

### 5.2 Metric SQL Builders

File:

`tools/metric_sql_builder.py`

These are not hardcoded one-off queries. They are reusable SQL builders for known metrics.

Supported metric builders:

- `enrollment_rate`
- `enrollment_gap`
- `serious_ae_count`
- `related_ae_count`
- `ae_rate_per_patient`
- `out_of_range_lab_rate`
- `net_sales`
- `units_sold`
- `net_sales_per_unit`

The builder:

1. Infers the metric from aliases.
2. Infers dimensions from phrases like `by country`, `by drug`, `by trial`, `by month`.
3. Infers ordering from words like `highest`, `lowest`, `top`, `bottom`.
4. Infers limit from phrases like `top 10`.
5. Returns SQL plus explanation and assumptions.

Example:

Question:

`Which drug was sold the most?`

Metric inferred:

`units_sold`

Dimension inferred:

`drug`

Generated SQL:

```sql
SELECT
  ds.drug_name AS drug_name,
  SUM(ds.units_sold) AS units_sold,
  ROUND(SUM(ds.net_sales), 2) AS net_sales,
  ROUND(SUM(ds.net_sales) / NULLIF(SUM(ds.units_sold), 0), 2) AS net_sales_per_unit,
  SUM(ds.units_sold) AS metric_value
FROM drug_sales ds
GROUP BY ds.drug_name
ORDER BY metric_value DESC
LIMIT 10
```

Why use metric builders:

- Known business metrics stay consistent.
- We can unit-test the SQL shape.
- The same metric definition is reused across questions.
- It reduces dependence on the LLM for common questions.
- It prevents mistakes like averaging percentages instead of dividing aggregate numerator by aggregate denominator.

## 6. How The LLM Creates SQL

When the LLM fallback is used, this happens:

1. `plan_query()` calls `_llm_plan(...)`.
2. `_llm_plan(...)` calls `build_llm_context(...)`.
3. `build_llm_context(...)` gathers:
   - relevant semantic context
   - compact schema
   - approved join paths
4. The LLM is instructed to return only JSON.
5. The JSON must contain:
   - `sql`
   - `explanation`
   - `assumptions`
   - `needs_python_analysis`
   - `recommended_python_analysis`
6. The SQL is immediately passed to `validate_sql(sql)`.
7. If validation fails, the plan fails and execution does not proceed.

Prompt constraints include:

- Generate one SQLite `SELECT` or `WITH` query only.
- Use only provided tables and columns.
- Use approved join paths.
- Prefer aggregate outputs.
- Avoid patient-level details unless explicitly necessary.
- Do not infer causality for adverse events.

The LLM does not directly execute SQL.

The LLM proposes SQL. The SQL tool decides whether it is safe to run.

## 7. How Context Is Managed

File:

`agent/context_builder.py`

The context builder avoids dumping everything into the LLM.

It builds:

### 7.1 Relevant Semantic Context

From:

- `semantic_layer/metric_definitions.yaml`
- `semantic_layer/ontology.yaml`
- `semantic_layer/business_glossary.yaml`
- `semantic_layer/join_paths.yaml`

The search is keyword-based right now.

### 7.2 Compact Schema Context

Instead of giving the LLM full database dumps, we provide table names and columns:

```text
- trials(trial_id, phase, therapeutic_area, ...)
- sites(site_id, trial_id, country, ...)
- drug_sales(sale_id, drug_name, country, month, ...)
```

### 7.3 Join Context

Approved joins come from:

`semantic_layer/join_paths.yaml`

Example:

```yaml
trials_to_sites:
  join_condition: trials.trial_id = sites.trial_id
```

### 7.4 Context Size Limit

`build_llm_context(..., max_chars=7000)` truncates the combined context if it gets too large.

This is basic but important. In a real office datamart with many tables, context management becomes one of the main engineering problems.

Future context strategy:

- Retrieve only relevant tables.
- Retrieve only relevant metric definitions.
- Retrieve only approved joins near those tables.
- Rank candidate tables by semantic match.
- Ask clarifying questions when multiple tables could answer the same question.
- Cache schema summaries.
- Use vector DB retrieval for unstructured knowledge base content.

## 8. SQL Safety

File:

`tools/sql_tool.py`

Important functions:

- `validate_sql(sql)`
- `maybe_add_limit(sql, limit=200)`
- `run_readonly_sql(sql, db_path, max_rows=200)`

Safety rules:

- Only one SQL statement is allowed.
- Only `SELECT` or `WITH` queries are allowed.
- Dangerous keywords are blocked:
  - `INSERT`
  - `UPDATE`
  - `DELETE`
  - `DROP`
  - `ALTER`
  - `CREATE`
  - `REPLACE`
  - `TRUNCATE`
  - `ATTACH`
  - `DETACH`
  - `PRAGMA`
  - `VACUUM`
- SQLite is opened with `mode=ro`.
- A `LIMIT` is added when one is missing.

Why this matters:

Even if an LLM generates bad SQL, the SQL tool prevents write/destructive operations from running.

## 9. Python Tooling

File:

`tools/python_tool.py`

The app does not execute arbitrary Python from the LLM.

Instead it supports predefined functions:

- `calculate_correlation`
- `calculate_summary_statistics`
- `calculate_trend`
- `calculate_percentage_change`
- `detect_simple_outliers`
- `create_chart_data`

The input is the SQL result:

```python
{
  "columns": [...],
  "rows": [...]
}
```

The Python tool converts that into a pandas DataFrame, performs the requested analysis, and returns JSON-serializable output.

Why not arbitrary Python:

- Arbitrary Python could read files, access network, leak data, or damage the environment.
- Predefined functions are safer and easier to test.
- This is sufficient for MVP analytics workflows.

## 10. Chart Creation

Chart planning happens in:

`agent/orchestrator.py`

Function:

`_recommend_chart(sql_result, python_result)`

Chart rendering happens in:

`app.py`

Functions:

- `_chart_frame(result)`
- `render_chart(result)`

### 10.1 How Chart Type Is Chosen

The app recommends:

| Result type | Chart type |
|---|---|
| Python trend result | line chart |
| Python percentage change result | line chart |
| Python outlier result | bar chart |
| SQL table with month as x-axis | line chart |
| SQL ranked/category table | bar chart |

### 10.2 How X And Y Axes Are Chosen

For Python trend:

- `x_col = "_period"`
- `y_col = "net_sales"`
- `group_by = "drug_name"`

For percentage change:

- `x_col = "month"`
- `y_col = "percentage_change"`
- `group_by = "drug_name"`

For outliers:

- `x_col = "month"`
- `y_col = "net_sales"`
- `group_by = "drug_name"`

For SQL-only results, the recommender checks column names in priority order.

Numeric y-axis priority:

1. `units_sold`
2. `net_sales`
3. `enrollment_rate_pct`
4. `serious_ae_count`
5. `out_of_range_rate_pct`
6. `adverse_event_count`
7. `patient_count`

Dimension x-axis priority:

1. `drug_name`
2. `trial_id`
3. `test_name`
4. `therapeutic_area`
5. `country`
6. `region`
7. `month`

The Streamlit UI uses Altair:

```python
base = alt.Chart(frame).encode(...)
chart = base.mark_line(point=True) if chart_type == "line" else base.mark_bar()
```

Why this approach:

- It is deterministic.
- It is easy to inspect.
- Later your production frontend can consume the same `chart_plan` object and render charts using your own UI library.

## 11. Frontend Rendering

File:

`app.py`

Streamlit is currently used as a testing cockpit, not the final platform UI.

It renders:

- Question type dropdown
- Question template dropdown
- Free-text question input
- Data catalog
- Final answer
- Chart tab
- Result table tab
- How it worked tab
- SQL tab
- Semantic context tab
- Python tab

The tabs are important because they separate:

- business-facing answer
- visual result
- source-of-truth table
- SQL audit trail
- semantic definitions
- Python/debug details

Why Streamlit:

- Fastest way to test the agent locally.
- No frontend build system needed.
- Easy table and chart rendering.
- Good for internal demos and iteration.

Why this is not the final frontend:

Your actual platform already has frontend patterns, auth, layout, state management, user roles, and deployment pipelines. Once the agent behavior is stable, this should become an API service and your platform frontend should render the response.

## 12. Data Tables In The Current Synthetic MVP

### 12.1 `trials`

One row per synthetic clinical trial.

Important columns:

- `trial_id`
- `phase`
- `therapeutic_area`
- `drug_name`
- `indication`
- `start_date`
- `end_date`
- `status`
- `country`
- `sponsor`
- `planned_enrollment`

Use for:

- Trial portfolio summaries
- Therapeutic area breakdowns
- Drug-to-trial mapping
- Trial status analysis

### 12.2 `sites`

Trial site enrollment data.

Important columns:

- `site_id`
- `trial_id`
- `country`
- `investigator_name`
- `enrollment_target`
- `enrolled_patients`

Use for:

- Enrollment rate
- Enrollment gap
- Site performance
- Country enrollment contribution

### 12.3 `patients`

Synthetic patient records with coarse demographics.

Important columns:

- `patient_id`
- `trial_id`
- `site_id`
- `age_group`
- `sex`
- `baseline_condition`
- `treatment_arm`

Use for:

- Patient counts
- Treatment arm distribution
- Demographic summaries

No real patient-identifiable data is used.

### 12.4 `adverse_events`

Synthetic adverse event data.

Important columns:

- `ae_id`
- `patient_id`
- `trial_id`
- `event_term`
- `severity`
- `seriousness`
- `outcome`
- `event_date`
- `related_to_drug`

Use for:

- Serious adverse event counts
- Related adverse event counts
- AE terms
- AE rate per patient

Important limitation:

AE outputs are descriptive only. The app must not claim causality.

### 12.5 `lab_results`

Synthetic lab test data.

Important columns:

- `lab_id`
- `patient_id`
- `trial_id`
- `test_name`
- `result_value`
- `unit`
- `normal_low`
- `normal_high`
- `result_date`

Use for:

- Out-of-range lab rate
- Lab summaries
- Test-level abnormality monitoring

### 12.6 `drug_sales`

Synthetic monthly commercial sales data.

Important columns:

- `sale_id`
- `drug_name`
- `country`
- `region`
- `month`
- `units_sold`
- `net_sales`
- `channel`
- `currency`

Use for:

- Units sold
- Net sales
- Net sales per unit
- Sales trends
- Sales by country, region, channel, drug

## 13. How To Test The Current App

Start the app:

```bash
cd pharma_analyst_agent
source .venv/bin/activate
streamlit run app.py
```

Run tests:

```bash
pytest
```

Current expected test count:

```text
33 passed
```

Manual app test questions:

| Question | Expected path | Expected behavior |
|---|---|---|
| `What does enrollment rate mean?` | semantic only | Shows definition, formula, cautions. |
| `Which drug was sold the most?` | metric SQL builder | Shows Neuroquel by units sold in current synthetic data. |
| `Which drug had the highest net sales?` | metric SQL builder | Shows Neuroquel by net sales in current synthetic data. |
| `Which trials have the highest enrollment rate?` | metric SQL builder | Shows top trials by enrollment rate. |
| `Show the top 10 trials by serious adverse event count.` | metric SQL builder | Shows serious AE counts with no-causality limitation. |
| `What is the out-of-range lab rate by test?` | metric SQL builder | Shows lab tests by out-of-range rate. |
| `Show monthly net sales trend by drug.` | Python template | SQL aggregation + Python trend + line chart. |
| `Calculate percentage change in monthly net sales by drug.` | Python template | SQL aggregation + Python percentage change + line chart. |
| `Find outliers in monthly net sales.` | Python template | SQL aggregation + Python IQR outlier detection. |
| `What is the correlation between enrolled patients and adverse event count?` | Python template | SQL aggregation + Python correlation. |
| `Which drug should this patient take?` | refusal | Refuses medical advice/treatment recommendation. |

How to inspect correctness:

1. Look at the answer.
2. Look at the chart.
3. Open the result table.
4. Open the SQL tab.
5. Confirm the SQL matches the business definition.
6. Open semantic context.
7. Open Python tab if Python was used.
8. Check `Planner source` in the `How it worked` tab.

Planner source meanings:

| Planner source | Meaning |
|---|---|
| `python_analysis_template` | A known SQL + Python analysis workflow was used. |
| `metric_sql_builder` | A unit-tested metric SQL builder created the query. |
| `llm_openrouter` | OpenRouter generated SQL, then SQL validation approved it. |
| `safe_fallback` | No known planner matched, so a default portfolio summary was used. |

## 14. Why We Built It This Way

### 14.1 Why Not Build Directly On The Platform First?

Building directly on the platform would combine too many risks at once:

- Agent planning risk
- SQL safety risk
- Semantic-layer design risk
- Data quality risk
- Platform auth and permissions risk
- Frontend integration risk
- Vector DB retrieval risk
- Production deployment risk

The current MVP isolates the core question:

Can we build an agent that understands a business question, chooses the right data workflow, executes safe tools, and explains the result?

Once that core is stable, platform integration becomes much easier.

### 14.2 Why SQLite?

SQLite is:

- local
- simple
- fast enough for MVP
- easy to inspect
- easy to reset
- good for testing SQL safety

In production, SQLite can be replaced by your actual datamart connection.

### 14.3 Why Streamlit?

Streamlit lets us build a testing frontend quickly.

It is not meant to replace your platform frontend.

### 14.4 Why YAML Semantic Layer?

YAML is transparent and easy to review with business users.

It lets us define:

- metrics
- glossary terms
- entities
- join paths

This creates a bridge between business definitions and SQL generation.

### 14.5 Why Metric Builders Instead Of Only LLM SQL?

Known metrics should be deterministic.

For metrics like enrollment rate or net sales per unit, the formula must be consistent every time.

Metric builders give us:

- consistency
- tests
- version control
- lower LLM cost
- fewer hallucinations
- easier stakeholder signoff

### 14.6 Why Still Use An LLM?

The LLM is useful for:

- long-tail questions
- flexible phrasing
- unknown combinations of dimensions
- planning SQL when no builder exists
- business-friendly summarization

But the LLM should be surrounded by guardrails.

## 15. Connecting To Your Office Datamart

The current project uses SQLite because it is local and synthetic. On your office computer, the goal is to point the same agent architecture at your actual datamart.

### 15.1 What Needs To Change

You will need to replace or extend:

| Current component | Datamart version |
|---|---|
| SQLite file path | Datamart connection string |
| `sqlite3` execution | connector for your DB, such as ODBC, SQL Server, Snowflake, Postgres, Databricks, etc. |
| SQLite syntax | target warehouse SQL dialect |
| synthetic semantic layer | semantic layer built from your real tables and Tableau definitions |
| synthetic metrics | approved business metrics from your dashboard/datamart |
| generated demo charts | charts based on your real dashboard specs |

### 15.2 New Database Tool

You should create a new DB tool, for example:

`tools/datamart_sql_tool.py`

It should preserve the same interface:

```python
run_readonly_sql(sql: str, db_path_or_conn: str, max_rows: int = 200) -> dict
```

But internally it would connect to your datamart instead of SQLite.

It still needs:

- read-only credentials
- SQL validation
- query timeout
- row limit
- audit logging
- error handling
- no write permissions

### 15.3 Schema Import Process

To connect your datamart:

1. Extract table names, column names, data types, primary keys, and foreign keys.
2. Generate an initial schema summary.
3. Identify the tables used by your Tableau dashboard.
4. Map Tableau measures to semantic metrics.
5. Map Tableau dimensions to semantic entities/dimensions.
6. Create join paths.
7. Add unit-tested metric SQL builders for your most important KPIs.
8. Enable LLM fallback only after builders and joins are verified.

### 15.4 Semantic Layer For Your Datamart

You will need a real semantic layer:

```text
semantic_layer/
  metric_definitions.yaml
  ontology.yaml
  business_glossary.yaml
  join_paths.yaml
  dashboard_specs.yaml
```

Recommended additions:

- owner of each metric
- source table
- source columns
- SQL expression
- approved dimensions
- default grain
- filter rules
- date logic
- caveats
- Tableau sheet/dashboard mapping

## 16. Replicating Your Tableau Dashboard

You currently have a manually built Tableau dashboard. The goal is to make the agent reproduce similar charts from the datamart.

The right way to approach this is not to ask the LLM to magically copy Tableau from a screenshot. Instead, convert the dashboard into a structured dashboard specification.

### 16.1 Extract Dashboard Metadata

For each Tableau sheet, document:

- chart title
- chart type
- data source/table
- measure
- dimensions
- filters
- date grain
- sort order
- top/bottom limits
- color encoding
- tooltip fields
- dashboard position

Example dashboard spec:

```yaml
dashboard_name: Sales Performance
charts:
  - chart_id: monthly_net_sales_by_drug
    title: Monthly Net Sales by Drug
    chart_type: line
    metric: net_sales
    dimensions:
      - month
      - drug_name
    x_axis: month
    y_axis: net_sales
    color_by: drug_name
    filters:
      date_range: last_24_months
```

### 16.2 Add Dashboard-Aware Chart Planning

Current chart planning is simple and column-based.

For Tableau replication, add:

`semantic_layer/dashboard_specs.yaml`

Then update chart planning to:

1. Detect dashboard intent.
2. Match question to chart spec.
3. Use metric SQL builder to create the query.
4. Return a chart plan that mirrors the Tableau sheet.
5. Render the chart in Streamlit or your platform frontend.

### 16.3 How The Agent Would Replicate A Tableau Chart

User asks:

`Show me the monthly net sales by product chart from my sales dashboard.`

Agent flow:

```text
Question
  -> retrieve dashboard spec
  -> identify chart_id = monthly_net_sales_by_drug
  -> metric = net_sales
  -> dimensions = month + drug_name
  -> SQL builder creates query
  -> SQL tool executes safely
  -> chart plan uses line chart
  -> frontend renders line chart with month on x, net_sales on y, drug_name as color
```

### 16.4 Matching The Dashboard Visually

First version:

- same metrics
- same dimensions
- same filters
- same chart type
- same x/y axes
- slightly different color palette allowed

Later version:

- same color palette
- same layout
- same number formatting
- same tooltips
- same dashboard-level filters
- same drilldowns
- same cross-filter behavior

## 17. What We Can Currently Do

Current capabilities:

- Local synthetic structured analytics.
- Safe SQL execution.
- Controlled Python analysis.
- Semantic definitions.
- Metric SQL builders.
- Optional LLM SQL planning.
- Optional LLM business summarization.
- Streamlit chart/table/source-of-truth UI.
- Unit tests.
- GitHub repo with committed code.

Current limitations:

- SQLite only for execution.
- Keyword semantic search, not vector search.
- LLM planner is available but not deeply evaluated yet.
- Chart planning is simple and column-based.
- No production auth or user permissions.
- No datamart connector yet.
- No Tableau metadata import yet.
- No dashboard layout replication yet.

## 18. Tough Questions And Good Answers

### Q: Is the LLM generating all SQL?

No for the synthetic pharma mode. Known workflows use deterministic templates and metric SQL builders. The LLM is used as a fallback planner when those do not cover the question and an LLM provider is configured.

For uploaded CSV mode, yes, the workflow is more agentic: the app loads the CSV into SQLite, sends the live schema and sample rows to the LLM, asks the LLM to generate SQL, validates that SQL, and then executes it read-only. Profile questions such as "what kind of data is this?" go through the CSV agent path and are summarized from the returned rows/columns. If the LLM fails in this mode, the app reports `llm_failed` instead of showing an unrelated fallback answer.

### Q: Why not let the LLM write everything?

Because business metrics must be consistent and testable. LLM-only SQL can hallucinate columns, use wrong joins, or calculate metrics inconsistently. Builders give us reliability for known metrics, while LLM fallback gives us flexibility.

### Q: What prevents unsafe SQL?

`tools/sql_tool.py` validates every SQL query. It allows only a single `SELECT` or `WITH` statement, blocks write/admin keywords, adds limits, and opens SQLite in read-only mode.

### Q: How does the agent know which tables to use?

For known metrics, `metric_sql_builder.py` knows the source tables and joins. For LLM fallback, `context_builder.py` provides relevant schema and approved join paths from the semantic layer.

### Q: How does it know which chart to create?

`orchestrator._recommend_chart()` inspects the result shape. Time-series outputs become line charts. Ranked/category outputs become bar charts. It chooses x/y columns using known priority lists.

### Q: What is the source of truth?

The SQL result table and Python analysis output are the source of truth. The final natural-language answer is just a formatted explanation of those results.

### Q: Can it use real data?

Architecturally yes, but we need a datamart connector, read-only credentials, real semantic definitions, production safety checks, and access controls before using real enterprise data.

### Q: How will this fit into our platform?

The Streamlit app should eventually be replaced by an API. Your platform frontend will call the agent API and render the returned answer, table, chart plan, SQL, semantic context, and citations.

### Q: How do we connect to an enterprise OpenAI-compatible endpoint?

Set `LLM_PROVIDER=custom_openai`, put the full chat-completions URL in `CUSTOM_OPENAI_CHAT_URL`, put the key in `CUSTOM_OPENAI_API_KEY`, and keep `CUSTOM_OPENAI_API_KEY_HEADER=api-key` if the gateway expects the header style shown in internal examples. The app sends the same chat-completions JSON payload directly to that URL.

## 19. Recommended Next Steps

### Step 1: Stabilize LLM Planner

- Add tests using OpenRouter planner outputs.
- Log LLM prompt, model, generated SQL, validation result.
- Add retry logic when LLM returns invalid JSON.
- Add a query approval screen for LLM-generated SQL.

### Step 2: Expand Metric Builders

Add builders for:

- patient count
- patient count by treatment arm
- AE term frequency
- AE severity distribution
- lab summary statistics
- sales by country
- sales by channel
- sales by region
- monthly units sold
- trial count by phase/status

### Step 3: Add Dashboard Specs

Create:

`semantic_layer/dashboard_specs.yaml`

Use it to define charts that mirror your Tableau dashboard.

### Step 4: Build Datamart Connector

Create a datamart SQL tool that mirrors the current SQL tool interface but connects to your office database.

### Step 5: Import Tableau Logic

Document each existing Tableau chart:

- metric
- dimensions
- filters
- joins
- chart type
- layout

Then convert that into semantic/dashboard YAML.

### Step 6: Add Platform API

Create an API endpoint:

```http
POST /agent/analyze
```

Request:

```json
{
  "question": "Show monthly sales by product",
  "user_id": "...",
  "workspace_id": "..."
}
```

Response:

```json
{
  "answer": "...",
  "table": {...},
  "chart_plan": {...},
  "sql": "...",
  "semantic_context": "...",
  "python_result": {...},
  "citations": [...]
}
```

### Step 7: Connect Knowledge Base And Vector DB

Your knowledge base can include:

- PDFs
- documents
- audio transcripts
- video transcripts
- text notes
- SOPs
- metric documentation
- dashboard documentation

Flow:

```text
User question
  -> classify structured vs unstructured vs mixed
  -> retrieve relevant KB chunks from vector DB
  -> retrieve relevant table/schema/metric context
  -> build SQL/Python plan
  -> execute tools
  -> combine computed evidence with KB citations
```

This lets the agent answer questions like:

`Why did this dashboard define active patients differently from enrolled patients?`

That may need both:

- datamart SQL
- documentation retrieval from vector DB

## 20. Final Mental Model

Think of the agent as four layers:

1. Frontend layer  
   Streamlit now, platform UI later.

2. Planning layer  
   Router, metric builders, Python templates, optional LLM planner.

3. Tool layer  
   SQL execution, Python analysis, schema inspection, semantic retrieval.

4. Governance layer  
   semantic definitions, join paths, safety validation, source-of-truth display, tests.

The current MVP proves the full loop locally. The next phase is to replace the synthetic SQLite backend with your office datamart and replace the simple chart recommender with dashboard-aware chart specs that can reproduce your Tableau dashboards.
