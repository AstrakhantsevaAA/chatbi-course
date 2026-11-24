---
name: add-metrics
description: Define named, agreed metrics in ontology.ison as a nodes.Metric section. Use after annotate-column-roles, so the same question always resolves to the same formula instead of an improvised aggregate.
---

# Add metrics

Without metrics, an agent asked "how much did I listen?" picks plays one time and minutes the next.
A metric fixes one agreed formula.

**Requires** `.schema/<cdm-name>/ontology.ison` and `.schema/<cdm-name>/CDM.dbml` with roles.

`create-ontology` excludes metrics on purpose: it may only describe columns that exist.
Metrics are agreed formulas over those columns, so they live in their own section.

## Steps

### 1. Collect the questions

Ask the user for the questions the data must answer, in their own words. Aim for one metric per question.

### 2. Propose one metric per question

Present this table and wait for confirmation:

| name | expression | table | filters | aliases |
|---|---|---|---|---|

Rules:
- `name` is snake_case.
- `expression` is real SQL over real CDM columns, qualified with the table name.
- `table` is the CDM table the metric is computed from (its FROM table).
- Put definition filters in `filters`, not in the user's head (for example `item_type = 'tracks'`).
- Guard the grain: through a bridge table, use `COUNT(DISTINCT <fact>.<key>)`.
- `aliases` are the phrasings people type, separated by `; `. Be generous.
- A metric that needs a subquery may use one; keep it read-only and portable.

### 3. Write them

Append a `nodes.Metric` section to `ontology.ison` (tab-separated, blank line before it):

```ison
nodes.Metric
name	display_name	expression	table	filters	aliases	description
plays	Plays	COUNT(fact_play.play_sk)	fact_play		plays; listens; streams; how often	Number of plays
```

### 4. Verify each metric

Run each metric through the `execute_sql_query` MCP tool:

```sql
SELECT <expression> AS value FROM <table> WHERE <filters or TRUE>
```

Each metric must return one plausible number. Ratios must be between 0 and 1.

## Output

- `.schema/<cdm-name>/ontology.ison` — a `nodes.Metric` section

Hand over to the `answer-question` skill.
