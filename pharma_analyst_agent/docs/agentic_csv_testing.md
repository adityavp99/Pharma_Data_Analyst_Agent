# Agentic CSV Testing Quick Start

This guide explains the fastest way to test the agent with your own CSV file and an optional Tableau/chart screenshot.

## 1. What Changed

The app now has two modes:

1. Synthetic pharma mode  
   Uses the existing local SQLite pharma MVP database, semantic layer, metric SQL builders, and optional LLM fallback.

2. Uploaded CSV agent mode  
   You upload a CSV in Streamlit. The app loads it into a temporary SQLite database and enables LLM-first SQL planning against the uploaded CSV schema.

This second mode is the one to use for agentic testing.

## 2. Configure OpenAI Or OpenRouter

Edit `.env`.

### Option A: OpenAI

Use this when you want to test with your OpenAI API key.

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_PLANNER_MODEL=gpt-4.1-mini
OPENAI_VISION_MODEL=gpt-4.1-mini

# Leave OpenRouter blank or unused
OPENROUTER_API_KEY=
```

### Option B: OpenRouter

Use this when you want the fallback/free OpenRouter route.

```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_PLANNER_MODEL=deepseek/deepseek-v4-flash:free
OPENROUTER_VISION_MODEL=deepseek/deepseek-v4-flash:free

# Leave OpenAI blank or unused
OPENAI_API_KEY=
```

### Option C: Enterprise/custom OpenAI-compatible endpoint

Use this when your organization gives you a full chat-completions endpoint URL and expects an `api-key` header, for example:

```text
https://.../openai/deployments/gpt-4o/chat/completions?api-version=...
```

Set:

```bash
LLM_PROVIDER=custom_openai
CUSTOM_OPENAI_CHAT_URL=https://your-org-endpoint/openai/deployments/gpt-4o/chat/completions?api-version=2023-03-15-preview
CUSTOM_OPENAI_API_KEY=your_enterprise_key_here
CUSTOM_OPENAI_API_KEY_HEADER=api-key
CUSTOM_OPENAI_MAX_TOKENS=1500

# Optional. Leave blank if the deployment is already in the URL.
CUSTOM_OPENAI_PLANNER_MODEL=
CUSTOM_OPENAI_VISION_MODEL=
```

Leave the public OpenAI/OpenRouter keys blank if you are using the enterprise endpoint.

Important: not every OpenRouter free model supports image input. If screenshot chart replication fails, use OpenAI vision or an OpenRouter model that supports images.

## 3. Run The App

```bash
cd pharma_analyst_agent
source .venv/bin/activate
streamlit run app.py
```

## 4. Test With Your CSV

1. Open the Streamlit app.
2. Upload your CSV under `Upload a CSV to test agentic analysis on your own data`.
3. Ask questions against your CSV columns.
4. Check:
   - answer
   - chart
   - result table
   - SQL tab
   - planner source

When a CSV is uploaded, planner source should usually be:

```text
llm_openai
```

or:

```text
llm_openrouter
```

If no key is configured, it will show:

```text
llm_failed
```

In the focused CSV test mode, unrelated fallback answers are disabled. If the LLM is not configured or the LLM call fails, the app will explicitly say the agentic task failed.

## 5. Example CSV Questions

Use questions like:

- What kind of data does this file contain? Show me a snippet of rows and columns.
- Describe this CSV so I know what questions to ask.
- Preview the rows and columns in this file.
- Show total sales by product.
- Show monthly revenue trend by region.
- Which customer segment has the highest margin?
- Show top 10 products by units sold.
- Compare revenue by channel and month.
- Create a bar chart of profit by category.
- Create a line chart of sales over time by region.

The LLM sees the uploaded table schema and generates SQLite SQL.

For preview/profile questions, the app intentionally returns a safe row preview first. That helps you inspect available columns before asking analytical questions.
The query is still planned through the CSV agent path; after the SQL result comes back, the configured LLM summarizes the columns and sample rows in plain English.

## 6. Test With A Tableau Screenshot

1. Upload your CSV.
2. Upload a screenshot of your Tableau chart.
3. Ask a question such as:

```text
Replicate this chart using the uploaded CSV.
```

The app will:

1. Use the LLM to create SQL over the CSV.
2. Use the screenshot to infer chart type, x-axis, y-axis, and grouping.
3. Render the closest matching Altair chart.

This is a prototype. It is meant to match the analytical structure first:

- chart type
- metric
- dimensions
- x/y axes
- grouping/color

Exact Tableau styling and layout come later.

## 7. Why This Is More Agentic

In uploaded CSV mode, the app is not relying on pharma-specific hardcoded SQL builders.

Instead:

1. It reads your CSV schema.
2. It gives that schema to the LLM.
3. The LLM decides which columns to use.
4. The LLM writes a SQLite `SELECT` query.
5. The SQL safety tool validates the query.
6. The query executes read-only.
7. The app renders the table and chart.

That is the intelligence layer:

- interpret question
- inspect available data
- plan SQL
- choose chart structure
- return explainable source-of-truth output

## 8. Current Limitations

- One uploaded CSV at a time.
- CSV is loaded into a temporary local SQLite table.
- The LLM creates SQL, but SQL must still pass validation.
- Screenshot chart replication is approximate.
- Exact Tableau dashboard layout replication is not built yet.
- Multi-table CSV/datamart joins need a richer semantic layer or uploaded relationship metadata.

## 9. Next Steps

1. Add support for multiple uploaded CSVs.
2. Add a UI for declaring joins between uploaded CSVs.
3. Add dashboard spec extraction for Tableau charts.
4. Add chart-plan editing before rendering.
5. Add SQL retry/repair when LLM SQL fails.
6. Add saved agent runs for comparison and evaluation.
7. Later, replace CSV upload with your office datamart connector.
