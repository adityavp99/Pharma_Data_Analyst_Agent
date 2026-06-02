# LangChain Agentic Pivot

## What Changed

The Streamlit app now points to a new LangChain-based agentic workflow under `langchain_agentic/`.

The old deterministic MVP files still exist in the repo for reference, but the active app no longer uses:

- deterministic question routing
- pharma semantic-layer matching
- hardcoded metric templates
- one-shot SQL planning
- fixed Python analysis selection

The active flow is now:

1. User uploads a CSV.
2. The app stores that CSV as a temporary SQLite table.
3. User asks one open-ended question.
4. LangChain `create_agent` starts a multi-step agent loop.
5. The LLM decides which tools to call, in what order, and how many times.
6. The tools return observations.
7. The LLM uses those observations to decide whether more tool calls are needed.
8. The LLM writes the final answer.
9. Streamlit renders the answer, latest SQL result, Python result, chart, and tool trace.

## Why This Is More Agentic

The previous version asked the LLM for one plan, then the Python code executed that plan.

The new version gives the LLM tools and lets it operate in a loop:

- It can inspect the dataset first.
- It can generate SQL after seeing the schema.
- It can revise its next step after seeing SQL results.
- It can run pandas analysis if SQL alone is not enough.
- It can propose a chart when a visual would help.
- It can answer open-ended questions like "what is this file about?"

The backend no longer decides "this is SQL only" or "this needs Python." The agent decides.

## Active Files

`app.py`

The Streamlit front end. It handles CSV upload, question input, and result rendering.

`langchain_agentic/llm_factory.py`

Builds the LangChain chat model from `.env`.

Supported providers:

- `azure_openai`
- `openai`
- `openrouter`

For the company Azure setup, use:

```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your_company_key_here
AZURE_OPENAI_ENDPOINT=https://genaiapimna.jnj.com/openai-chat
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-10-21
```

`langchain_agentic/agent.py`

Creates the LangChain agent and exposes tools:

- `inspect_dataset`
- `query_dataset_sql`
- `run_python_analysis`
- `propose_chart`

The tools are general data-analysis capabilities. They are not pharma-specific.

`tools/csv_tool.py`

Still used only to load the uploaded CSV into SQLite.

`tools/sql_tool.py`

Still used as a minimal read-only SQL execution boundary. This is not business logic; it is a runtime safety boundary.

## Tools The Agent Can Use

### inspect_dataset

Returns:

- table row counts
- schema
- sample rows
- column data types
- null counts
- unique counts
- simple numeric summaries

The agent should call this when it does not yet understand the uploaded CSV.

### query_dataset_sql

Runs one SQLite `SELECT` or `WITH` query.

The LLM writes the SQL. The tool executes it read-only and returns the result.

### run_python_analysis

Runs local pandas analysis against dataframe `df`.

The LLM writes the pandas code. The code should assign its output to `result`.

This is useful for:

- correlations
- trend calculations
- reshaping
- custom summaries
- exploratory profiling

This is a local prototype tool. Before platform deployment, replace this with a proper sandboxed code execution service.

### propose_chart

The LLM calls this when it wants the UI to render a chart.

The agent chooses:

- chart type
- x-axis column
- y-axis column
- optional group/color column
- chart title
- whether the chart should use the latest SQL result or uploaded dataframe

Streamlit only renders the chart spec. It does not decide which chart should be created.

## How To Run

Install dependencies:

```bash
cd pharma_analyst_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `.env`:

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

Run:

```bash
streamlit run app.py
```

## What To Test First

Upload a CSV and ask:

```text
What kind of data does this file contain? Show me the columns, sample rows, and what questions I can ask.
```

Expected behavior:

- agent calls `inspect_dataset`
- answer summarizes the uploaded file
- no unrelated fallback answer
- trace tab shows the tool call

Ask:

```text
Which category or product has the highest total sales? Show the calculation and create a chart.
```

Expected behavior:

- agent inspects or directly writes SQL
- agent calls `query_dataset_sql`
- agent may call `propose_chart`
- UI shows a table and chart

Ask:

```text
Is there a monthly trend in revenue? Use Python if needed and visualize it.
```

Expected behavior:

- agent uses SQL or Python depending on the columns it finds
- agent proposes a line chart if date and numeric columns exist
- answer explains the evidence

## Why We Are Not Using The Platform Yet

This local version isolates the hard part: can an LLM reason over structured data and orchestrate tools?

Starting locally is useful because:

- CSV upload is fast to test.
- SQLite is simple and transparent.
- Tool traces are visible.
- We can debug SQL, Python, and chart decisions before adding enterprise integration.
- We avoid mixing agent-design risk with platform-integration risk too early.

Once the loop works on CSVs, the same agent shape can be pointed at datamarts instead of uploaded files.

## How This Moves Toward Datamarts And Tableau Replacement

Next, replace the uploaded CSV source with a datamart connector.

The future tools become:

- inspect available datamarts
- inspect table schemas
- query approved datamart views
- join across approved views
- create KPI cards
- create chart specs
- generate dashboard/report layouts
- explain the source tables and calculations

The same LangChain loop remains: the LLM decides which tool to call next.

For Tableau replication, add:

1. A screenshot interpretation tool.
2. A chart-spec generation tool.
3. A dashboard layout tool.
4. A validation step comparing chart columns and aggregations against the uploaded CSV/datamart.

## When LangGraph Becomes Necessary

Do not add custom LangGraph graphs yet.

LangChain `create_agent` already uses the modern agent runtime and is enough for the first agentic CSV/datamart testing.

Move to explicit LangGraph when you need:

- human approval steps
- multiple specialist agents
- long-running workflows
- persistent memory/checkpoints
- retries with branch logic
- formal review stages
- dashboard generation pipelines with several fixed phases

For now, the fastest path is:

1. Prove the agent loop on uploaded CSVs.
2. Add better tools.
3. Add datamart connectors.
4. Add chart/dashboard generation.
5. Then formalize the workflow with LangGraph if the process needs durable state and branching.
