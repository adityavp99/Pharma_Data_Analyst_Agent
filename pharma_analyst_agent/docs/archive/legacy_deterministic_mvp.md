# Legacy Deterministic MVP Notes

This note is kept only for historical reference.

The first version of the project used a deterministic workflow:

- synthetic pharmaceutical data generation
- a hand-written semantic YAML layer
- a rule-based router that chose SQL, Python, semantic-only, or mixed flows
- predefined metric templates
- a simple one-shot planning style

That approach was useful for proving the basic idea:

- structured data can be loaded locally
- SQL can answer aggregate questions
- Python can handle post-query analysis
- metric definitions can help keep answers consistent
- safe execution guardrails are necessary

However, it was not the desired final direction because too much behavior was hardcoded. The current active app has moved to a LangChain `create_agent` loop where the LLM chooses tools dynamically based on the question and previous tool results.

The legacy deterministic files were removed from the active workspace to avoid confusion. The active implementation is documented in the root `README.md`.
