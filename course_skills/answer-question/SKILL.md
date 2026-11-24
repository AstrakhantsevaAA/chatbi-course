---
name: answer-question
description: Answer a business question about the listening_activity data with gated, read-only SQL. Use when the user asks a question about their plays, saved tracks, playlists, artists, or top items, or a follow-up to a previous answer.
argument-hint: "[question]"
---

# Answer a question

Three steps: **plan → gate → answer**. You plan and write SQL. `gate.py` checks both, with no model.
A Claude Code hook also runs the gate before every `execute_sql_query` on the CDM, so a rejected
query never reaches the warehouse.

**Requires** the `listening_activity_cdm` pipeline, `.schema/listening_activity/ontology.ison` with
metrics, `CDM.dbml` with roles, and `gate.py` in the project root.

## Steps

### 1. Load the context (once per session)

```bash
uv run python gate.py context
```

This prints every CDM table with column roles, every metric, and every entity. Use only these names.

### 2. Decide if you can answer

- **Out of scope** (no entity or metric relates to it, for example the weather): say so in one
  sentence and stop. Do not query.
- **Ambiguous** (two metrics or entities fit and give different numbers): ask one short clarifying
  question that names the options, and stop.
- **Follow-up** ("and for last month?", "only playlists"): start from the previous plan and change
  only what the user changed. Keep every filter the user did not withdraw.

### 3. Write the plan and gate it

Write `.chatbi/plan.json`:

```json
{
  "question": "<the user's words>",
  "concepts": ["Play", "Artist"],
  "metrics": ["plays"],
  "group_by": ["dim_artist.artist_name"],
  "filters": ["fact_play.played_at >= CURRENT_DATE - INTERVAL '7' DAY"],
  "time_range": "last 7 days",
  "assumptions": ["Plays count every play, including repeats"]
}
```

Rules:
- If a metric matches the question or its aliases, you **must** use it. Never improvise an aggregate
  that a metric already defines.
- `group_by` uses `table.column` with role `dimension`, `time_dimension`, or `label`.
- To filter on a `dimension` value you have not seen, first read its values (at most 3 probes):
  `SELECT <col>, COUNT(*) FROM <table> GROUP BY 1 ORDER BY 2 DESC LIMIT 20`.
- Time words have one meaning each. Write the one you used in `assumptions`:

  | The user says | Filter (DuckDB) |
  |---|---|
  | today | `>= CURRENT_DATE` |
  | this week | `>= DATE_TRUNC('week', CURRENT_DATE)` (calendar week, from Monday) |
  | last 7 days, past week | `>= CURRENT_DATE - INTERVAL '7' DAY` |
  | this month / this year | `>= DATE_TRUNC('month' / 'year', CURRENT_DATE)` |
  | last 30 days | `>= CURRENT_DATE - INTERVAL '30' DAY` |
  | no time word | all data; say which period the data covers |

- "Library" means liked songs plus tracks in playlists I own or collaborate on (`library_songs`).
  Liked songs alone are "liked songs". Followed playlists have no tracks in the data.

```bash
uv run python gate.py check-plan .chatbi/plan.json
```

If REJECTED, fix the plan once with the reasons. If it is still REJECTED, tell the user why and stop.

### 4. Write the SQL and gate it

Write `.chatbi/query.sql`. Use metric expressions and filters **verbatim**. Join facts to dimensions
on `*_sk`, and to artists through `bridge_track_artist`. Add `LIMIT` (at most 200).
For rankings, break ties by name: `ORDER BY <metric> DESC, <label>`. If the last row of a top N
ties with rows below it, say so in the answer.

```bash
uv run python gate.py check-sql .chatbi/query.sql
```

If REJECTED, fix it once. If it is still REJECTED, tell the user why and stop.

### 5. Run it

Call the `execute_sql_query` MCP tool with `pipeline_name: "listening_activity_cdm"` and the SQL.

Check the result before you answer:
- **Empty:** check the data range (`SELECT MIN(played_at), MAX(played_at) FROM fact_play LIMIT 1`)
  and say if the question asks about a period outside it.
- **Impossible values** (negative counts, ratios above 1): fix the SQL once, or report the problem.

### 6. Answer

Reply in this order:
1. The answer in one or two sentences, with the number.
2. The metric used (or "no metric: <why>").
3. The rows as a small markdown table (at most 10 rows).
4. The SQL in a `sql` block.
5. Assumptions, including data limits (play history starts at the first load).

Append one line to `answers_log.jsonl`. `value` is the headline number of the answer (the first
row's metric value for a ranking), or `null` when there is no number:

```json
{"question": "...", "status": "answered | clarified | out_of_scope | rejected", "metric": "...", "value": 0, "sql": "...", "rows": 0}
```
