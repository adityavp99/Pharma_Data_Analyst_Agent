# Dashboard Reverse-Engineering Test Plan

Use this when you have two or more CSV extracts that were combined to create a Tableau dashboard.

The goal is not to ask "make the chart" immediately. The goal is to backtrack like an analyst:

1. understand each file
2. infer how the files connect
3. validate candidate joins
4. map filters
5. map metrics
6. reproduce one table of chart-ready data
7. render the closest chart
8. list missing semantic information

## Setup

Upload:

- the two CSV files
- the reference dashboard screenshot
- the DML/source SQL file, if available

In **Manual chart replication context**, add anything you know:

```text
Dashboard name = Sales Value
Chart type = multi-series monthly line chart
Geography = Australia
Therapeutic Area = Multiple Myeloma
Brand = DARZALEX
Sales Organisation = Oncology
Time Period = MTH
Rolling Period = 1 Year Dynamic
Forecast = N
Element = ALL
Additional KPI = none
Expected series = current period value, previous period value, target, projection if available
```

## Phase 1: File And Grain Understanding

Ask:

```text
Inspect both uploaded tables. For each table, identify the row count, likely grain, likely key columns, time columns, dimensions, measures, and any columns that look relevant to the dashboard screenshot. Do not create a chart yet.
```

Expected value:

- tells you what each file represents
- identifies whether one file is fact-like and another is dimension/target/filter-like
- surfaces missing or confusing columns early

Follow-up:

```text
Compare the two tables. Which columns have the same or similar names, and which columns look like possible join keys? For each candidate join, explain why it might work and what risk it has.
```

## Phase 2: Join Validation

Ask:

```text
For the strongest candidate join keys, run SQL checks to validate the relationship between the two tables. Show joined row counts, unmatched records on each side if possible, duplicate key risks, and whether the join looks one-to-one, one-to-many, many-to-one, or many-to-many.
```

Expected value:

- prevents wrong joins from producing misleading charts
- reveals whether Tableau likely used a relationship, blend, or pre-joined extract

If the agent is unsure, ask:

```text
What additional semantic information would you need to confidently join these two tables?
```

## Phase 3: Filter Mapping

Ask:

```text
Using the screenshot and manual chart context, map each visible dashboard filter to actual columns in the uploaded tables. Validate the available values for Australia, Multiple Myeloma, DARZALEX, Oncology, MTH, Forecast=N, Element=ALL, and any rolling period fields. Do not apply a filter unless the value exists.
```

Expected value:

- tells you whether filters are present in the data
- catches cases where values use different names or codes
- prevents random filter invention

Follow-up:

```text
Which requested filters are missing, ambiguous, encoded differently, or only available after joining the tables?
```

## Phase 4: Metric And Series Mapping

Ask:

```text
Map the screenshot series to data columns or calculations. I need current period value, previous period value, target, and projection if available. For each series, say whether it is directly available as a column, calculated from DML, or missing/ambiguous. Do not create the final chart yet.
```

Expected value:

- identifies whether the chart can actually be recreated
- separates data columns from Tableau calculations
- surfaces missing target/projection logic

Follow-up:

```text
Using the DML context, explain any MAT, MQT, rolling period, current period, previous period, target, or projection logic that appears relevant. State which parts are confirmed and which are assumptions.
```

## Phase 5: Chart-Ready SQL

Ask:

```text
Create chart-ready SQL for the Sales Value line chart. The output should be monthly grain and should include one row per month with columns for current_value, previous_value, target_value, and projection_value only if projection exists. Apply only validated filters. Show the SQL and the resulting table before proposing a chart.
```

Expected value:

- this is the most important checkpoint
- if this table is wrong, the chart will be wrong
- you can compare the table against Tableau labels

If the values are mostly zero or wrong, ask:

```text
The chart-ready result does not match the screenshot. Diagnose why. Check whether this is caused by wrong filters, wrong join, wrong time grain, missing current/previous period logic, target/projection mapping, zero actuals, or missing source rows.
```

## Phase 6: Render The Chart

Ask:

```text
Using the chart-ready SQL result, render a multi-series line chart. X-axis should be month. Y-axis should be Sales Value. Use red for current period value, light gray for previous period value, black for target, and blue only for projection if projection exists. Explain any mismatch versus the screenshot.
```

Expected value:

- produces a useful approximation
- clearly states if Tableau logic is still missing

## Phase 7: Missing Semantic Layer Inventory

Ask:

```text
Based on everything you found, create a missing semantic layer checklist for this dashboard. Include required metric definitions, filter mappings, join keys, date grain rules, current/previous period logic, target/projection logic, Tableau calculations, and any DML/Tableau metadata we still need.
```

Expected value:

- turns agent failure into a concrete implementation roadmap
- tells you exactly what metadata is required for production

## Best Demo Question

Use this for a boss-friendly demo:

```text
Reverse engineer this dashboard chart using the uploaded CSVs, DML, screenshot, and manual context. Do not try to perfectly copy Tableau first. Instead, identify the table relationship, validate filters, map each chart series, generate chart-ready SQL, render the closest line chart, and list exactly what metadata is missing for perfect replication.
```

This demonstrates real value even when the final chart is not perfect.
