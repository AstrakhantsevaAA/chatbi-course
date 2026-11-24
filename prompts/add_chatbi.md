# Prompt: extend the dashboard with ChatBI

Paste this into Claude Code after `my_music_history.py` works and the semantic layer
exists (`.schema/listening_activity/CDM.dbml` with roles, `ontology.ison` with metrics)
and `gate.py` passes `uv run python gate.py --self-test`.

---

```text
Extend my_music_history.py with a chat that answers questions about my data.
Write the logic in a new module chatbi.py, keep the notebook cell thin, and add
stub-client tests in tests/test_chatbi.py.

GOAL
A last section "Ask my music data": I type a question, the app answers with the
number first, shows the rows and the SQL that ran. It must never write data and
never use a table or column that is not in the CDM.

DESIGN: A WORKFLOW, NOT AN AGENT
Code controls every step; the model only fills two of them:
1. PLAN (model): plan + one SQL query as structured output.
2. GATE (no model): gate.check_plan + gate.check_sql. If rejected, send the reasons
   back for ONE repair; if still rejected, show the reasons and stop.
3. RUN (no model): the gated SQL, read-only, on the CDM.
4. ANSWER (model): a short answer written from the rows.

CLAUDE API
- Python `anthropic` SDK (uv add anthropic), Messages API, model "claude-opus-5-5"
  (allow override with the CHATBI_MODEL env var).
- client.beta.messages.create with betas=["server-side-fallback-2026-07-01"] and
  fallbacks="default" (server-side refusal fallback). Check stop_reason == "refusal"
  before reading content.
- Plan step: output_config={"effort": "medium", "format": {"type": "json_schema",
  "schema": PLAN_SCHEMA}}. Answer step: output_config={"effort": "low"}.
- PLAN_SCHEMA (all fields required, additionalProperties false): status (enum
  answer | clarify | out_of_scope | write_request), clarifying_question, concepts,
  metrics, group_by, filters, assumptions (arrays of strings), sql (string).
- No temperature/top_p/top_k, no thinking budget, no assistant prefill.
- Credentials: use the AGENT__API_KEY env var or dlt.secrets "agent.api_key" when
  present, else anthropic.Anthropic() with no arguments. Never print or log the key.

PLAN PROMPT (system prompt = these rules + gate.context(gate.load_cdm()))
- Use only listed tables, columns, metrics, entities. Never invent names.
- A metric that matches the question or its aliases must be used verbatim.
- group_by is table.column with role dimension, time_dimension, or label.
- One read-only SELECT, LIMIT <= 200, no SELECT *; join facts to dimensions on *_sk,
  artists through bridge_track_artist; ties: ORDER BY <metric> DESC, <label>.
- Time words: today >= CURRENT_DATE; this week >= DATE_TRUNC('week', CURRENT_DATE);
  last 7 days >= CURRENT_DATE - INTERVAL '7' DAY; this month/year DATE_TRUNC.
- "Library" = liked songs + tracks in playlists I own or collaborate on
  (library_songs); followed playlists have no tracks in the data.
- Plays exist only since the first load (Spotify keeps 50): say so in assumptions.
- status write_request for delete/update/insert requests, out_of_scope when no data
  relates, clarify when two readings give different numbers; none of them has SQL.
- Follow-ups change only what the user changed: send the plans of the last 3 answered
  turns with the new question.

RUN
- cdm_dataset()(sql).df() from destinations.py: duckdb on the local dev profile,
  playground on dltHub, always with an explicit destination and dataset, because a
  dltHub run has no local pipeline state. The app runs on the read-only access
  profile there.

ANSWER PROMPT
- Input: question, metrics, assumptions, the first 20 rows, the row count (JSON).
- Output: number first in one or two sentences, one line naming the metric, one
  sentence on data limits, plain markdown, no tables, at most 80 words.

NOTEBOOK CELL (last cell before `if __name__ == "__main__":`)
- import chatbi inside the cell; keep a list of earlier turns in the cell.
- mo.ui.chat(fn, prompts=[4 example questions]) where fn(messages, config) answers
  messages[-1].content and returns mo.vstack([mo.md(answer), mo.ui.table(rows,
  selection=None) when there are rows, mo.accordion({"SQL (passed the gate)": sql})]).
- Catch exceptions and return "Sorry, I could not answer: <error>" so the chat keeps
  working.
- Header text: questions run through plan -> gate -> read-only SQL; every answer
  shows its SQL.

TESTS (tests/test_chatbi.py, stub client, no API key, no warehouse)
1. Answered: gated SQL runs; the first request has fallbacks="default" and a
   json_schema format.
2. A gate rejection gets exactly one repair, and the repair prompt holds the reasons.
3. DELETE SQL is still rejected after the repair.
4. write_request is refused with no SQL and one model call.
5. out_of_scope runs no SQL.
6. A follow-up sends the earlier plan.

CHECK
- uv run python -m unittest discover -s tests -t .
- uvx marimo check my_music_history.py
- uv run marimo export html my_music_history.py -o /tmp/report.html and confirm
  0 cell errors (no "vnd.marimo+error").
- uv run dlthub deploy, then open the app and ask one prompt-button question.
```

---

**Expected result:** `chatbi.py`, a chat section at the end of `my_music_history.py`,
6 passing stub tests, a clean `marimo check`, and an answer with its SQL in the deployed
app.
