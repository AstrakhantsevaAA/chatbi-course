"""ChatBI for the data app: plan, gate, run read-only SQL, answer.

The same loop as the answer-question skill, as code: Claude writes a plan and SQL
as structured output, gate.py checks both with no model, the SQL runs on the CDM,
and Claude writes a short answer from the rows. Used by my_music_history.py.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

import anthropic
import dlt

import gate
from destinations import cdm_dataset

MODEL = os.getenv("CHATBI_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_ROWS_SHOWN = 20

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answer", "clarify", "out_of_scope", "write_request"]},
        "clarifying_question": {"type": "string"},
        "concepts": {"type": "array", "items": {"type": "string"}},
        "metrics": {"type": "array", "items": {"type": "string"}},
        "group_by": {"type": "array", "items": {"type": "string"}},
        "filters": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "sql": {"type": "string"},
    },
    "required": ["status", "clarifying_question", "concepts", "metrics", "group_by",
                 "filters", "assumptions", "sql"],
    "additionalProperties": False,
}

PLAN_RULES = """You answer questions about one person's Spotify listening data.
You write a plan and one DuckDB SQL query over the CDM below. Rules:
- Use only the tables, columns, metrics, and entities listed. Never invent names.
- If a metric matches the question or its aliases, use its expression and filters verbatim.
- group_by uses table.column with role dimension, time_dimension, or label.
- One read-only SELECT, LIMIT 200 at most, no SELECT *. Join facts to dimensions on *_sk
  and to artists through bridge_track_artist. Break ties with ORDER BY <metric> DESC, <label>.
- Time words: today = >= CURRENT_DATE; this week = >= DATE_TRUNC('week', CURRENT_DATE);
  last 7 days = >= CURRENT_DATE - INTERVAL '7' DAY; this month/year = DATE_TRUNC('month'/'year').
- "Library" = liked songs plus tracks in playlists I own or collaborate on (library_songs).
  Followed playlists have no tracks in the data.
- Plays exist only since the first load (Spotify keeps 50); say so in assumptions when
  the question uses plays.
- status write_request when the user asks to change data (delete, update, insert; no SQL);
- status out_of_scope when nothing in the data relates to the question (no SQL);
  status clarify when two readings give different numbers (one short question, no SQL).
- A follow-up question changes only what the user changed; keep earlier filters.
Leave unused fields as empty strings or empty lists.

CDM, metrics, and entities:
"""

ANSWER_RULES = """Write the answer to the user's question from the query result.
Start with the answer and the number in one or two sentences. Then one short line naming
the metric used. Mention data limits from the assumptions in one sentence. Plain markdown,
no tables (the app shows the rows), at most 80 words."""


@dataclass
class Turn:
    """One answered question: what the app shows and what a follow-up builds on."""

    question: str
    status: str
    answer: str
    sql: str = ""
    rows: Any = None
    plan: dict = field(default_factory=dict)


def make_client() -> anthropic.Anthropic:
    """Use the dltHub agent key when present, else the SDK's own credentials."""
    key = os.getenv("AGENT__API_KEY") or dlt.secrets.get("agent.api_key")
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def _call(client: Any, system: str, messages: list, effort: str, schema: dict | None) -> str:
    """Call Claude with refusal fallback and return the text of the reply."""
    output_config: dict = {"effort": effort}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    response = client.beta.messages.create(
        model=MODEL, max_tokens=16000, betas=[FALLBACK_BETA], fallbacks="default",
        system=system, messages=messages, output_config=output_config,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined this question.")
    return next(b.text for b in response.content if b.type == "text")


def _history(turns: list[Turn]) -> str:
    """Summarize earlier turns so a follow-up can keep their filters."""
    lines = [f"Q: {t.question}\nplan: {json.dumps(t.plan)}" for t in turns[-3:] if t.plan]
    return ("Earlier questions in this chat:\n" + "\n".join(lines) + "\n\n") if lines else ""


def plan(client: Any, question: str, turns: list[Turn], cdm: dict, feedback: str = "") -> dict:
    """Ask Claude for a plan and SQL as structured output."""
    system = PLAN_RULES + gate.context(cdm)
    content = _history(turns) + f"Question: {question}"
    if feedback:
        content += f"\n\nYour previous plan was rejected by the gate. Fix it:\n{feedback}"
    return json.loads(_call(client, system, [{"role": "user", "content": content}], "medium",
                            PLAN_SCHEMA))


def gate_reasons(p: dict, cdm: dict) -> list[str]:
    """Run both deterministic gates on a plan and its SQL."""
    plan_check = {**p, "question": "chat"}
    return gate.check_plan(plan_check, cdm) + gate.check_sql(p["sql"], cdm)


def run_sql(sql: str) -> Any:
    """Run gated, read-only SQL on the CDM and return a DataFrame."""
    return cdm_dataset()(sql).df()


def ask(question: str, turns: list[Turn], client: Any = None, runner: Any = run_sql) -> Turn:
    """Answer one question: plan, gate (one repair), run, answer."""
    client = client or make_client()
    cdm = gate.load_cdm()
    p = plan(client, question, turns, cdm)
    if p["status"] == "out_of_scope":
        return Turn(question, "out_of_scope",
                    "That is outside my data: I only know your Spotify library, playlists, "
                    "plays, and top lists.")
    if p["status"] == "write_request":
        return Turn(question, "rejected", "I only read your data. I can't change or delete anything.")
    if p["status"] == "clarify":
        return Turn(question, "clarified", p["clarifying_question"])
    reasons = gate_reasons(p, cdm)
    if reasons:
        p = plan(client, question, turns, cdm, feedback="\n".join(reasons))
        reasons = gate_reasons(p, cdm) if p["status"] == "answer" else ["no SQL after repair"]
    if reasons:
        return Turn(question, "rejected", "The gate rejected the query:\n- " + "\n- ".join(reasons),
                    sql=p.get("sql", ""), plan=p)
    rows = runner(p["sql"])
    payload = {"question": question, "metrics": p["metrics"], "assumptions": p["assumptions"],
               "rows": rows.head(MAX_ROWS_SHOWN).to_dict(orient="records"),
               "row_count": len(rows)}
    answer = _call(client, ANSWER_RULES,
                   [{"role": "user", "content": json.dumps(payload, default=str)}], "low", None)
    return Turn(question, "answered", answer, sql=p["sql"], rows=rows, plan=p)
