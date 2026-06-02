# LangChain Agentic Data Analyst MVP

Local proof-of-concept for a generalized data analyst agent that can reason over an uploaded CSV, decide which tools to use, run multi-step analysis, and produce answer/table/chart outputs.

The active Streamlit app is now a LangChain agentic CSV lab. The older synthetic pharma dataset, semantic layer, deterministic router, and metric templates are still in the repo as reference/history, but `app.py` now uses the new LangChain loop under `langchain_agentic/`.

## What The Active App Does

- Upload a CSV.
- Store it as a temporary local SQLite table.
- Let a LangChain `create_agent` loop decide what to do.
- Give the agent tools for dataset inspection, SQL querying, pandas analysis, and chart proposal.
- Render the final answer, latest SQL result, Python result, chart, and agent tool trace.

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

## Active Architecture

1. `app.py` receives CSV upload and question.
2. `tools/csv_tool.py` loads the CSV into SQLite.
3. `langchain_agentic/llm_factory.py` builds the LLM client.
4. `langchain_agentic/agent.py` creates a LangChain agent with tools.
5. The agent decides whether to call:
   - `inspect_dataset`
   - `query_dataset_sql`
   - `run_python_analysis`
   - `propose_chart`
6. Streamlit renders the result and tool trace.

For a detailed explanation of this pivot, see [`docs/langchain_agentic_pivot.md`](docs/langchain_agentic_pivot.md).

## Legacy Reference Components

The repo still includes the earlier pharma-focused MVP components:

- Synthetic CSV generator for trials, sites, patients, adverse events, lab results, and drug sales.
- SQLite loader with indexes.
- Semantic YAML files.
- Deterministic router.
- Metric SQL builders.
- Controlled predefined Python analysis tools.

These are useful references, but they are not the active Streamlit app flow after the LangChain pivot.

To generate the old synthetic data:

```bash
python scripts/generate_synthetic_data.py
python scripts/load_sqlite.py
```

## Safety Notes

- CSV upload mode is for local testing.
- SQL execution is still read-only.
- The local pandas code tool is for prototype testing only.
- Before platform deployment, replace local Python execution with a sandboxed execution service.
- Do not use real patient-identifiable data in this local prototype.

## Suggested Next Steps

- Test the LangChain loop with real datamart-shaped CSV extracts.
- Add datamart connector tools.
- Add approved SQL/view-access tools.
- Add chart/dashboard spec tools.
- Add screenshot-to-chart-spec tooling for Tableau replication.
- Add stronger execution sandboxing before production or platform exposure.
- Move to explicit LangGraph only when the workflow needs durable state, approvals, retries, or multiple specialist agents.

For the longer previous workbook, see [`docs/agent_workbook.md`](docs/agent_workbook.md).
