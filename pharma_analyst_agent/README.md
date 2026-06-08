# LangChain Agentic Data Analyst MVP

Local proof-of-concept for a generalized data analyst agent that can reason over an uploaded CSV, decide which tools to use, run multi-step analysis, answer follow-up questions, and produce answer/table/chart outputs.

The workspace has been cleaned around the LangChain agentic CSV lab. The old synthetic pharma dataset generator, semantic layer, deterministic router, one-shot planner, and metric templates have been removed to avoid confusion.

## What The Active App Does

- Upload a CSV.
- Optionally upload DML/SQL context that contains source logic, calculated fields, MQT/MAT-style formulas, and filters.
- Optionally upload a Tableau/chart screenshot as visual context when the configured model supports image input.
- Store it as a temporary local SQLite table.
- Let a LangChain `create_agent` loop decide what to do.
- Give the agent tools for dataset inspection, SQL querying, pandas analysis, chart option inspection, and chart proposal/validation.
- Render the final answer, latest SQL result, Python result, chart, and agent tool trace.
- Preserve chat history so users can ask follow-up questions.

The backend no longer decides "SQL only" or "Python needed" through a deterministic router. The LLM decides which tool to call next based on observations from previous tool calls.

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

For a detailed explanation of this pivot, see [`docs/langchain_agentic_pivot.md`](docs/langchain_agentic_pivot.md).

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

These are the main pieces of code owned by this project:

- `app.py`: Streamlit CSV upload, chat UI, result tabs, chart rendering, and session state.
- `langchain_agentic/agent.py`: `AgenticCSVAnalyst`, system prompt, LangChain `create_agent` call, and tool definitions.
- `langchain_agentic/llm_factory.py`: provider selection for Azure OpenAI, OpenAI, and OpenRouter.
- `langchain_agentic/charting.py`: chart column role detection, chart validation, compact `YYYYMM` date handling, and Plotly figure creation.
- `langchain_agentic/guardrails.py`: request guardrails and Python AST/code guardrails.
- `langchain_agentic/metadata_context.py`: DML/SQL context parser for tables, CTEs, calculated aliases, metric snippets, and filters.
- `tools/csv_tool.py`: CSV-to-SQLite loading and safe table naming.
- `tools/sql_tool.py`: read-only SQL validation and execution.
- `tools/schema_tool.py`: SQLite schema, row count, and table preview helpers.

LangChain provides the agent runtime through `create_agent`. The LLM provider supplies the model. Everything above is the local orchestration, tool, UI, validation, and guardrail layer we wrote ourselves.

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

1. Test with real datamart-shaped CSV extracts and collect failure cases.
2. Add a safer Python execution service or disable Python for demos where risk is unacceptable.
3. Add better chart-spec output, including KPI cards, multi-chart report sections, and dashboard layout.
4. Add datamart connector tools that expose only approved schemas/views.
5. Add metadata retrieval so the agent can handle many tables without stuffing all context into the prompt.
6. Add a query approval step for large/expensive datamart queries.
7. Add evaluation tests for 30-50 realistic questions.
8. Add Tableau screenshot interpretation once CSV/datamart question answering is stable.
9. Move to explicit LangGraph when we need durable multi-stage workflows, approvals, retries, or multiple specialist agents.
