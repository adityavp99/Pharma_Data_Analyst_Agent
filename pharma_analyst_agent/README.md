# LangChain Agentic Data Analyst MVP

Local proof-of-concept for a generalized data analyst agent that can reason over an uploaded CSV, decide which tools to use, run multi-step analysis, answer follow-up questions, and produce answer/table/chart outputs.

The workspace has been cleaned around the LangChain agentic CSV lab. The old synthetic pharma dataset generator, semantic layer, deterministic router, one-shot planner, and metric templates have been removed to avoid confusion.

## What The Active App Does

- Upload a CSV.
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
- Chart proposals are now validated before rendering.
- Plotly charts are more interactive than the previous basic Altair charts.
- The project is small enough to move quickly.
- Azure OpenAI, OpenAI, and OpenRouter provider paths are separated cleanly.
- The code is now easier to map to future datamart tools because the tools are generic.

## Major Gaps To Explore And Fix

- **Python sandboxing:** the pandas tool currently runs local model-generated code with restricted builtins. This is fine for local testing, but not enough for production.
- **Data permissions:** uploaded CSV testing does not yet model user-level datamart permissions.
- **Large data:** the current CSV-to-SQLite path is not designed for very large enterprise datamarts.
- **Context management:** the agent only sees recent chat turns and tool outputs. For many tables, we will need schema retrieval, table selection, and possibly a metadata/vector layer.
- **Chart sophistication:** chart specs are validated now, but dashboard-level layout, KPI cards, advanced formatting, and Tableau-like replication still need dedicated tools.
- **Reliability evaluation:** we need a test set of realistic business questions with expected SQL/outputs.
- **Human approval:** there is no approval checkpoint before expensive queries or report publishing.
- **Observability:** we show a local trace, but production needs logs, cost tracking, latency, and failure categorization.
- **Guardrails:** read-only SQL is enforced locally, but enterprise guardrails should come from approved libraries/services.

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

### Chart Quality

```text
Create the best chart for comparing total revenue by product. If the first chart choice is not suitable, fix it before answering.
```

```text
Create a trend chart, but first aggregate the data to the right grain so the chart is not too crowded.
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
