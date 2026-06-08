# LangChain Agentic Data Analyst MVP

Local proof-of-concept for a generalized data analyst agent that can reason over an uploaded CSV, decide which tools to use, run multi-step analysis, answer follow-up questions, and produce answer/table/chart outputs.

Historical notes are archived under [`docs/archive`](docs/archive). The root README describes only the active LangChain agentic CSV application.

## What The Active App Does

- Upload a CSV.
- Optionally upload DML/SQL context that contains source logic, calculated fields, MQT/MAT-style formulas, and filters.
- Optionally upload a Tableau/chart screenshot as visual context when the configured model supports image input.
- Store it as a temporary local SQLite table.
- Let a LangChain `create_agent` loop decide what to do.
- Give the agent tools for dataset inspection, SQL querying, pandas analysis, chart option inspection, and chart proposal/validation.
- Render the final answer, latest SQL result, Python result, chart, and agent tool trace.
- Preserve chat history so users can ask follow-up questions.

## Quick Start Guide

### Step 1: Initial Setup

```bash
# Navigate to the project directory
cd pharma_analyst_agent

# Create a Python virtual environment
python -m venv .venv

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install all required dependencies
pip install -r requirements.txt

# Copy environment configuration
cp .env.example .env
```

Configure your company Azure OpenAI endpoint in `.env`:

```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your_company_key_here
AZURE_OPENAI_ENDPOINT=https://genaiapimna.jnj.com/openai-chat
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-10-21
AGENT_RECURSION_LIMIT=12
AGENT_MAX_SQL_ROWS=1000
AGENT_ENABLE_PYTHON_TOOL=true
```

### Step 2: Launch The Application

```bash
# Start the Streamlit web application
streamlit run app.py
```

Upload a CSV and ask:

```text
What kind of data does this file contain? Show me sample rows, columns, and useful questions I can ask.
```

### Step 3: Run Tests

```bash
pytest
```

## Current Architecture

1. `app.py` receives CSV upload and chat messages.
2. `tools/csv_tool.py` loads the CSV into SQLite.
3. `langchain_agentic/llm_factory.py` builds the LLM client.
4. `langchain_agentic/agent.py` creates a LangChain agent with tools.
5. The agent decides whether to call:
   - `inspect_dataset`
   - `inspect_business_context`
   - `inspect_data_quality`
   - `query_dataset_sql`
   - `run_python_analysis`
   - `inspect_chart_options`
   - `propose_chart`
6. Streamlit stores recent user/assistant turns in session state so follow-ups have context.
7. Streamlit validates the final chart spec again before rendering it with Plotly.
8. Streamlit renders the result and tool trace.

## Current Context/Semantic Layer

The current app uses a lightweight context layer that gives the agent business meaning without hardcoding every metric.

The context layer currently comes from:

- **Uploaded CSV schema:** table name, columns, row count, sample rows, column profiles, likely dimensions, likely measures, and likely time columns.
- **Uploaded DML/SQL file:** parsed as metadata only. It extracts tables/views, CTE names, calculated aliases, `WHERE` filters, and metric snippets such as MAT, MQT, YTD, QTD, MTD, TRx, NRx, and NBRx.
- **Manual dashboard/filter notes:** user-provided notes such as `Timeperiod=MTH`, `geography_lvl1=Australia`, or `brandgroup=overall/no filter`.
- **Screenshot visual context:** optional image context for models that support vision.
- **Tool outputs:** SQL results, data quality summaries, chart options, and chart validation feedback.

This is a practical MVP semantic layer. It is not yet a production metric registry. Production should add governed metric definitions, dashboard metadata extraction, data catalog integration, and possibly vector retrieval over business documentation.

## What Is Good Right Now

- The active flow is genuinely agentic: the LLM chooses tool calls in a loop.
- The UI is simple: upload CSV, then chat.
- Tool traces make the agent behavior inspectable.
- SQL is still read-only.
- User request guardrails refuse unsafe requests such as credential extraction, medical advice, prompt extraction, and bulk data dumping.
- Python code guardrails block imports, file/database reads and writes, unsafe builtins, and overly complex snippets.
- The agent can inspect data quality: missing values, duplicate rows, likely key columns, cardinality, and numeric ranges.
- The agent can inspect uploaded DML/SQL business context, including table references, calculated aliases, filters, and MQT/MAT-like snippets.
- Chart proposals are now validated before rendering.
- Plotly charts are more interactive than the previous basic Altair charts.
- Compact period columns such as `202506` are treated as year-month time dimensions, not numeric measures.
- The project is small enough to move quickly.
- Azure OpenAI, OpenAI, and OpenRouter provider paths are separated cleanly.
- The code is now easier to map to future datamart tools because the tools are generic.

## Best Value-First Use Cases

The fastest path is not to position the MVP as a full Tableau replacement. Full Tableau replication requires a mature semantic layer, Tableau calculated fields, LOD expressions, parameter logic, filter state, and dashboard metadata.

The strongest near-term use cases are:

1. **Datamart Understanding Assistant**
   - User uploads a datamart-shaped CSV.
   - Agent explains the grain, columns, likely dimensions, likely measures, time fields, data quality issues, and useful questions.
   - Value: helps analysts and business users understand unfamiliar data quickly.

2. **Dashboard QA / Reverse-Engineering Assistant**
   - User uploads CSV, DML/source SQL, screenshot, and optional chart notes.
   - Agent explains what filters, measures, axes, and calculations are needed to reproduce the dashboard chart.
   - Value: helps diagnose whether the chart is reproducible from the available data before trying to automate it.

3. **KPI Explanation Assistant**
   - User uploads DML/source SQL.
   - Agent explains MAT, MQT, current period, previous period, target, projection, and other KPI logic in plain English.
   - Value: reduces dependency on reading raw SQL/Tableau logic.

4. **Data Quality And Reporting Readiness Assistant**
   - Agent checks missing periods, zero values, duplicate rows, suspicious measures, high-cardinality filters, and likely key columns.
   - Value: practical, easy to demonstrate, and directly useful before a dashboard build or data refresh.

5. **Ad Hoc Analytics Assistant**
   - User asks one focused business question at a time.
   - Agent inspects data, validates filters, runs SQL, proposes a chart, and explains the calculation.
   - Value: faster one-off analysis without manually building a new Tableau sheet.

Recommended demo framing:

```text
This prototype is a datamart analyst copilot. It helps users understand structured data, validate dashboard logic, detect data quality issues, and generate first-pass analytical views. It is not yet a governed Tableau replacement, but it shows how an agent can reduce manual analysis and dashboard debugging effort.
```

## Major Gaps To Explore And Fix

- **Python sandboxing:** the pandas tool now has AST-based guardrails, but it is still local model-generated code execution. Production should use a proper sandboxed execution service.
- **Data permissions:** uploaded CSV testing does not yet model user-level datamart permissions.
- **Large data:** the current CSV-to-SQLite path is not designed for very large enterprise datamarts.
- **Context management:** the agent only sees recent chat turns and tool outputs. For many tables, we will need schema retrieval, table selection, and possibly a metadata/vector layer.
- **Chart sophistication:** chart specs are validated now, but dashboard-level layout, KPI cards, advanced formatting, and Tableau-like replication still need dedicated tools.
- **Column semantics:** obvious date patterns such as `YYYYMM`, `YYYY`, and date strings are detected, but business-specific metric definitions still need metadata/datamart context.
- **Tableau replication:** uploaded DML and screenshots provide useful context, but exact Tableau parity still needs Tableau calculated-field extraction, dashboard filter metadata, and visual validation.
- **Reliability evaluation:** we need a test set of realistic business questions with expected SQL/outputs.
- **Human approval:** there is no approval checkpoint before expensive queries or report publishing.
- **Observability:** we show a local trace, but production needs logs, cost tracking, latency, and failure categorization.
- **Guardrails:** local request, SQL, chart, and Python guardrails exist now, but enterprise deployment should still use approved guardrail/sandbox/audit services.

## Core Functions We Wrote

These are the main pieces of code owned by this project. They are functions/classes we wrote ourselves, even though they call LangChain, pandas, SQLite, Plotly, and Streamlit internally.

- `app.py`
  - `render_agent_chart`
  - `render_trace`
  - `render_result_details`
  - Streamlit upload/chat/session orchestration
- `langchain_agentic/agent.py`
  - `AgenticCSVAnalyst`
  - `_build_tools`
  - `run`
  - `_profile_frame`
  - `_data_quality_summary`
  - `_diagnostic_result`
  - tool wrappers: `inspect_dataset`, `inspect_business_context`, `inspect_data_quality`, `inspect_column_values`, `query_dataset_sql`, `run_python_analysis`, `inspect_chart_options`, `propose_chart`
- `langchain_agentic/llm_factory.py`
  - provider selection for Azure OpenAI, OpenAI, and OpenRouter
- `langchain_agentic/charting.py`
  - `infer_column_role`
  - `convert_temporal_series`
  - `summarize_chart_options`
  - `validate_chart_plan`
  - `build_plotly_chart`
  - multi-series line/bar/area support for wide chart data
- `langchain_agentic/guardrails.py`
  - `check_user_request`
  - `validate_python_analysis_code`
- `langchain_agentic/metadata_context.py`
  - `summarize_sql_context`
  - SQL/DML parsing helpers for tables, CTEs, calculated aliases, metric snippets, and filters
- `tools/csv_tool.py`
  - `safe_table_name`
  - `load_csv_to_sqlite`
- `tools/sql_tool.py`
  - `validate_sql`
  - `maybe_add_limit`
  - `run_readonly_sql`
- `tools/schema_tool.py`
  - `get_schema`
  - `describe_table`
  - `get_table_row_counts`
  - `get_schema_text`

## Library Functions We Call

These are not functions we wrote. They are important library/runtime capabilities that our code calls.

- **LangChain / LangGraph**
  - `langchain.agents.create_agent`: creates the agent loop.
  - `langchain_core.tools.tool`: turns Python functions into callable agent tools.
  - `agent.invoke`: runs the agent reasoning/tool-call loop.
  - `GraphRecursionError`: raised when the agent uses all allowed reasoning/tool-call steps.
- **LLM provider wrappers**
  - Azure/OpenAI/OpenRouter chat model classes are used by `llm_factory.py`.
  - The model decides which tool to call next and writes SQL/Python/chart plans.
- **pandas**
  - `pd.read_csv(..., chunksize=...)`: streams large CSV files in chunks.
  - DataFrame profiling, type conversion, and local analysis.
  - `DataFrame.to_sql`: writes chunks into SQLite.
- **SQLite / sqlite3**
  - stores uploaded CSV data as a local SQL table.
  - executes read-only analytical SQL.
- **sqlparse**
  - parses and validates SQL shape.
  - helps split statements and strip comments.
- **Plotly Express**
  - renders validated chart plans into interactive charts.
- **Streamlit**
  - file upload, sidebar controls, chat UI, tabs, dataframes, and chart display.

## DML And Tableau Context Workflow

You can now upload an optional `.sql` or `.txt` file containing DML/source SQL. The app parses it as context only; it does not execute it.

The parser extracts:

- referenced tables/views
- CTE names
- calculated fields and aliases
- `WHERE` filters
- metric snippets involving terms like `MAT`, `MQT`, `YTD`, `QTD`, `MTD`, `TRx`, `NRx`, and `NBRx`
- a raw SQL excerpt for additional context

The agent gets this through the `inspect_business_context` tool. It should use the context to understand how columns and metrics are used, then generate read-only analysis SQL against the uploaded CSV table.

You can also upload a Tableau/chart screenshot. If your configured Azure/OpenAI model supports image input, the screenshot is passed to the agent as visual context. The agent can use it to infer chart type, axes, groupings, labels, and likely filters, then validate those choices against the CSV and DML context.

This is the right direction, but it is still an approximation. Exact Tableau replication usually needs more than a screenshot:

- Tableau calculated fields
- dashboard filter settings
- parameter values
- LOD expressions
- table calculations
- worksheet shelf configuration
- data source relationships/joins
- default date grains and sort orders

The easier production path is to provide metadata in this order:

1. CSV/datamart extract for the actual data.
2. DML/source SQL for metric and filter logic.
3. A short dashboard/filter note explaining default filters and front-end selections.
4. Screenshot only as visual guidance.
5. Later, replace manual uploads with automated metadata extraction from Tableau/datamart/catalog APIs.

The UI now also has a **Manual chart replication context** box. Use this when the screenshot is ambiguous or when the filter state is not visually obvious.

Example:

```text
Timeperiod = MTH
geography_lvl1 = Australia
brandgroup = overall / no filter
TA = overall / no filter
DA = overall / no filter
x-axis = year_month
y-axis = sales_value
chart type = line
color = use Tableau-like blue/orange series colors if grouping is present
```

The agent prompt treats these manual notes as stronger evidence than screenshot inference. If you say `brandgroup=overall/no filter`, the agent should not randomly select a brand group from the CSV.

## Large CSV Uploads

Streamlit normally limits uploaded files to 200 MB. This repo now includes `.streamlit/config.toml` with:

```toml
[server]
maxUploadSize = 1024
```

That raises the upload limit to 1 GB for local testing.

`tools/csv_tool.py` also loads CSVs into SQLite in chunks instead of reading the entire file into one pandas DataFrame. This is important for files with 1M+ rows or 500 MB+ size.

The chunking method is pandas streaming chunking:

```python
pd.read_csv(file_obj, chunksize=100_000, low_memory=False)
```

That returns one DataFrame chunk at a time. The first chunk creates/replaces the SQLite table. Later chunks append to the same table.

Why this chunking approach was chosen:

- It is simple and already supported by pandas.
- It avoids holding the entire CSV in memory during import.
- It works with the current SQLite-backed MVP.
- It keeps the rest of the app unchanged because the agent still queries one SQLite table.

This is row-based chunking for ingestion, not LLM context chunking. The LLM does not read every chunk. The large CSV becomes a SQLite table, then the agent uses SQL to inspect and aggregate it.

What this improves:

- The browser/server can accept larger CSV files.
- The app avoids one giant in-memory pandas load during import.
- The SQLite table is reused during the chat session instead of being reloaded on every Streamlit rerun.
- The agent can query and aggregate the large file through SQL.

What this does not solve yet:

- Very large files can still take several minutes to upload and import.
- Local disk speed and available RAM still matter.
- The LLM should never receive all raw rows. It should inspect schema/sample rows and run SQL aggregations.
- For production datamarts, uploading 500 MB CSVs is a testing bridge, not the final architecture. A direct database connector or governed extract service is better.

Recommended first tests for a large file:

```text
What kind of data does this file contain? Show me the row count, columns, likely date columns, likely dimensions, and likely measures.
```

```text
Inspect the data quality. Which columns have missing values, high cardinality, or look like IDs?
```

```text
Using the uploaded DML context, identify which columns are likely used for the MAT/MQT KPI logic.
```

Then ask for one chart at a time:

```text
Using the uploaded DML and screenshot as guidance, recreate the main monthly trend chart as closely as possible. First explain the inferred filters, x-axis, y-axis, grouping, and aggregation, then generate the chart.
```

For a 500 MB+ CSV, avoid broad requests like "recreate the whole dashboard" in one turn. Ask for one KPI card, one trend, or one comparison at a time.

## Why Desired Charts Can Still Be Wrong

The current chart flow is useful, but it is not yet Tableau-grade.

What works:

- The model can infer common chart types such as line, bar, scatter, and area.
- The model can inspect chartable columns before proposing a chart.
- The app validates that x/y/group columns exist.
- The app blocks obvious mistakes such as using `year_month` as a y-axis measure.
- Compact dates like `202506` are treated as time dimensions.
- Plotly renders the final validated chart.

Why it can still fail:

- A screenshot does not always expose all active filters.
- The model may over-infer filters from visible labels or random column values.
- Tableau may use hidden calculated fields, parameters, LOD expressions, or table calculations that are not present in the CSV.
- The uploaded CSV may be at a different grain than the Tableau chart.
- The chart may require one or more frontend filters that are not visible in the screenshot.
- The Python tool has guardrails and can reject model-generated code as "too complex" if the code is too long or has too many AST nodes.
- LangChain provides the agent loop, but it does not guarantee correct business semantics. The model still needs metadata and validation.

What was improved in the current foundation:

- The agent can inspect distinct filter values before writing final SQL.
- Multi-series line charts are supported through either long-form data with `group_by` or wide-form data with multiple y columns.
- Manual chart notes are treated as stronger evidence than screenshot inference.
- The prompt tells the agent not to invent hidden brand, TA, DA, geography, or product filters.

How to get better results now:

- Provide manual chart context for filters and axes.
- Ask for one chart at a time.
- Tell the agent which column is the time field and which column is the measure.
- State filters explicitly, especially when they are "overall/no filter."
- Ask the agent to explain inferred filters before rendering.
- Prefer SQL aggregation for simple dashboard charts.

Example prompt:

```text
Using the CSV, uploaded DML, screenshot, and manual chart context, recreate the simple Australia monthly line chart.
Use Timeperiod=MTH, geography_lvl1=Australia, no brandgroup filter, no TA filter, and no DA filter.
First state the inferred chart spec and filters. Then run SQL to aggregate to monthly grain and render the line chart.
```

## Recursion Limit And Error Diagnostics

LangChain `create_agent` runs as a graph-style loop. Each model step and tool call consumes part of the recursion budget. If the agent keeps calling tools and never produces a final answer, LangGraph raises a recursion-limit error.

The app now catches this and shows a `Diagnostics` tab with:

- exception type and message
- recursion limit used
- likely causes
- tool call counts
- recent tool events
- latest SQL/Python/chart state
- full traceback

Common causes of recursion-limit errors:

- The agent keeps trying to repair invalid SQL.
- The agent keeps trying to repair blocked Python code.
- The agent keeps trying to repair an invalid chart.
- The question asks for too many outputs in one turn, such as multiple KPI cards, multiple charts, data quality, and narrative insight all at once.
- The uploaded CSV does not contain the columns needed for the requested analysis.
- The model repeatedly misunderstands a business-specific column name because no metadata/dictionary exists yet.

When this happens, reframe the question into one smaller task:

```text
First, inspect the dataset and identify the date, dimension, and measure columns.
```

Then:

```text
Now create one monthly revenue trend using year_month as the time axis and revenue as the measure.
```

## Other Errors You May See

- **LLM/provider errors:** wrong endpoint, expired key, blocked network, unavailable deployment, or model not supporting tool calls.
- **SQL errors:** nonexistent columns, wrong table name, invalid SQLite syntax, or unsafe SQL blocked by the read-only validator.
- **Python guardrail errors:** model-generated code tried imports, file access, database access, unsafe builtins, or overly complex logic.
- **Chart validation errors:** wrong y-axis, too many categories, invalid chart type, missing chart columns, or using a date as a measure.
- **CSV loading errors:** malformed CSV, unsupported encoding, duplicate weird headers, or very large files.
- **Data interpretation errors:** ambiguous column names, missing metadata, business-specific abbreviations, or multiple possible grains.

## Questions And Framing That Do Not Work Well Yet

Avoid asking for too much in one turn:

```text
Create a full dashboard with all KPIs, trends, segments, outliers, recommendations, and explain everything.
```

Ask in stages instead:

```text
Identify the likely KPIs in this dataset.
```

```text
Create one KPI summary table.
```

```text
Now create a monthly trend chart for the most important measure.
```

Avoid vague metric names if the CSV does not contain clear columns:

```text
Show performance.
```

Better:

```text
Use revenue as the performance measure and compare it by product and month.
```

Do not ask for row-level dumps:

```text
Show all rows.
```

Better:

```text
Show a 10-row sample and summarize the main columns.
```

Do not ask for clinical, medical, legal, regulatory, or treatment recommendations. The agent is only for analytical exploration of structured data.

## What Else To Test

Start with one CSV that resembles one of your real datamarts. Then test these categories:

### Dataset Understanding

```text
What kind of data does this file contain? Explain the columns, likely grain, sample rows, and what questions I can ask.
```

```text
What are the likely dimensions, measures, date columns, and ID columns in this dataset?
```

### KPI-Style Questions

```text
What are the top 5 products by total revenue? Show the calculation and create a bar chart.
```

```text
Calculate total revenue, total units, average revenue per unit, and number of unique customers.
```

### Trend Analysis

```text
Show monthly revenue trend by region. Create a line chart and explain the biggest changes.
```

```text
Compare this quarter versus last quarter for revenue and units. Show percentage change.
```

### Segmentation

```text
Which customer segment contributes the most revenue, and how does that differ by region?
```

```text
Break down sales by product and channel. Highlight the top combinations.
```

### Outlier And Data Quality

```text
Find unusual spikes or outliers in revenue. Use Python if needed and explain your method.
```

```text
Check for missing values, duplicate IDs, strange date ranges, and columns that may need cleaning.
```

```text
Inspect data quality first, then tell me whether this file is safe to use for KPI reporting.
```

### Chart Quality

```text
Create the best chart for comparing total revenue by product. If the first chart choice is not suitable, fix it before answering.
```

```text
Create a trend chart, but first aggregate the data to the right grain so the chart is not too crowded.
```

```text
Use year_month as the monthly time axis, not as a measure. Show monthly revenue trend.
```

### Follow-Up Chat

After one answer, ask:

```text
Now show the same analysis by region.
```

```text
Turn that into a line chart instead.
```

```text
Explain the SQL you used in simple terms.
```

```text
What business action would you recommend investigating next, without claiming causality?
```

## Safety Notes

- CSV upload mode is for local testing.
- SQL execution is still read-only.
- The local pandas code tool is for prototype testing only.
- Before platform deployment, replace local Python execution with a sandboxed execution service.
- Do not use real patient-identifiable data in this local prototype.

## Suggested Next Steps

1. Pick one high-value use case first: datamart understanding, dashboard QA, KPI explanation, or data quality readiness.
2. Test with 3-5 real datamart-shaped CSV extracts and collect repeatable failure cases.
3. Build a small governed metric/context pack for only one dashboard family, not all dashboards.
4. Add a dashboard QA mode that always outputs: inferred filters, metric mapping, SQL, chart, mismatch notes, and data quality warnings.
5. Add datamart connector tools that expose only approved schemas/views.
6. Add metadata retrieval so the agent can handle many tables without stuffing all context into the prompt.
7. Add evaluation tests for 30-50 realistic questions.
8. Add a safer Python execution service or disable Python for demos where risk is unacceptable.
9. Move to explicit LangGraph when we need durable multi-stage workflows, approval checkpoints, retries, evaluator agents, or multiple specialist agents.
