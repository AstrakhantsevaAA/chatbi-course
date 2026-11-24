---
name: annotate-column-roles
description: Give every CDM column a semantic role (dimension, measure, time_dimension, identifier) in CDM.dbml. Use after create-transformation, before add-metrics, so an answering agent knows what to group by, what to aggregate, and what holds time.
---

# Annotate column roles

An answering agent reads `CDM.dbml` to write SQL. Roles tell it how to use each column.

**Requires** `.schema/<cdm-name>/CDM.dbml` and a CDM that has been built (run `create-transformation` first).

## Roles

| Role | Meaning | The agent may |
|---|---|---|
| `identifier` | Surrogate keys, natural keys, foreign keys | Join on it. Never aggregate or show it |
| `dimension` | Categorical value | Group by it, filter on it, read its DISTINCT values |
| `time_dimension` | Date or timestamp | Group by a period of it, filter on a range |
| `measure` | Numeric value that adds up | SUM, AVG, MIN, MAX |
| `label` | Human-readable name | Show it in answers; filter with ILIKE |

## Steps

### 1. Propose a role for every column

Read `CDM.dbml`. Propose one role per column with this table, and wait for confirmation:

| Table | Column | Proposed role | Why |
|---|---|---|---|

Rules:
- `*_sk`, `source_id`, and `*_id` columns are `identifier`.
- A number that does not add up (rank, position, year) is a `dimension`, not a `measure`.
- A column that holds a few repeated values (status, type, time_range) is a `dimension`.

### 2. Check the dimensions against real data

For each proposed `dimension`, run a read-only query through the `execute_sql_query` MCP tool:

```sql
SELECT <column>, COUNT(*) AS n FROM <table> GROUP BY 1 ORDER BY 2 DESC LIMIT 20
```

If a column has more than about 50 distinct values, change it to `label`.
Do not write the values into any file: the agent reads them fresh at question time.

### 3. Write the roles

Add the role to each column's note in `CDM.dbml`. Keep any note text that is already there:

```dbml
  time_range varchar [note: 'role: dimension; short_term ~4 weeks, medium_term ~6 months, long_term ~1 year']
  duration_ms bigint [note: 'role: measure; full track length, not time listened']
```

### 4. Verify

Every column in `CDM.dbml` has exactly one `role:`. Count the columns without one; the count must be 0.

## Output

- `.schema/<cdm-name>/CDM.dbml` — a `role:` on every column

Hand over to `add-metrics`.
