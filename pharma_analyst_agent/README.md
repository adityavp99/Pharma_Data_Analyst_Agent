# Pharma Analyst Agent MVP

Local proof-of-concept for a generalized data analyst agent over synthetic pharmaceutical-style structured data.

The MVP shows how an agent can route a natural-language analytics question to a semantic layer, read-only SQL, and controlled Python analysis without using real patient-identifiable data.

## What It Includes

- Synthetic CSV generator for trials, sites, patients, adverse events, lab results, and drug sales.
- SQLite loader with indexes for common joins and filters.
- Semantic layer for metrics, ontology, and business glossary.
- Read-only SQL tool with mutation/admin command blocking.
- Controlled Python analysis tool using predefined pandas/numpy functions only.
- Deterministic tool router and orchestrator.
- Streamlit UI for local demos.
- Pytest coverage for SQL safety, semantic loading, and sample questions.

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

The app works without an OpenAI API key because this MVP includes deterministic routing and SQL templates. The prompt files are included so an OpenAI-compatible tool-calling planner can be added cleanly later.

### Step 2: Generate and Load Synthetic Data

```bash
# Generate synthetic pharmaceutical data
python scripts/generate_synthetic_data.py

# Load the data into SQLite
python scripts/load_sqlite.py
```

This creates:

- `data/raw/trials.csv` — Clinical trial master data
- `data/raw/sites.csv` — Trial site enrollment and target data
- `data/raw/patients.csv` — Patient demographics and enrollment
- `data/raw/adverse_events.csv` — Reported adverse events by patient/trial
- `data/raw/lab_results.csv` — Patient lab test results with normal ranges
- `data/raw/drug_sales.csv` — Monthly drug sales data
- `data/processed/pharma_mvp.db` — SQLite database with indexes

### Step 3: Launch the Application

```bash
# Start the Streamlit web application
streamlit run app.py
```

The application will open in your browser at `http://localhost:8501`. You can now start querying the synthetic pharmaceutical data.

### Step 4: Run Tests (Optional)

```bash
# Execute all test suites
pytest

# Run with verbose output
pytest -v

# Test specific modules
pytest tests/test_sql_safety.py          # Test SQL injection prevention
pytest tests/test_semantic_layer.py      # Test semantic layer loading
pytest tests/test_sample_questions.py    # Test end-to-end question routing
```

## Architecture

The flow is:

1. User asks a natural-language question.
2. `agent/tool_router.py` decides whether the question needs semantic context, SQL, Python, or refusal.
3. `tools/semantic_tool.py` retrieves relevant metric, ontology, or glossary context.
4. `agent/orchestrator.py` creates a read-only SQL plan for supported MVP question types.
5. `tools/sql_tool.py` validates SQL, rejects unsafe statements, opens SQLite in read-only mode, and returns rows.
6. `tools/python_tool.py` runs only predefined analysis functions when extra post-query computation is needed.
7. `agent/response_formatter.py` formats the final answer with evidence, SQL, assumptions, and limitations.

## Safety Notes

- All data is synthetic.
- Patient IDs are synthetic IDs.
- SQL execution allows only one `SELECT` or `WITH` statement.
- User-facing SQL rejects mutation, DDL, admin, attach/detach, vacuum, and pragma commands.
- Python analysis does not run arbitrary model-generated code.
- Adverse event analysis is descriptive only and does not infer causality.
- The final answer must show evidence and limitations.

## Suggested Next Steps

- Replace deterministic SQL templates with an LLM planner using the prompts in `agent/prompts.py`.
- Add a query approval/debug screen in Streamlit.
- Expand the semantic layer and add unit-tested metric SQL builders.
- Add chart rendering for trend and distribution outputs.
- Add a vector database only after keyword semantic search becomes limiting.
- Add LangChain, LlamaIndex, or OpenAI Agents SDK once the plain orchestration contract is stable.


- Have a sematic layer ready, with sql templates if not should use LLMs to generate on the fly. 
- Should figure out how to deal with context especially as it could greatly increase in volume. 
- Use internal guardrails libraries for LLM guardralis and other existing libraries. 