"""Deterministic gate between an answering agent and the warehouse.

Commands: `context` prints the CDM and metrics for the agent; `check-plan FILE`
and `check-sql FILE` print APPROVED or REJECTED with reasons; `hook` runs as a
Claude Code PreToolUse hook on execute_sql_query; `--self-test` runs the cases.
No model is called here: the gate is wrong the same way every time.
"""

import json
import sys
from pathlib import Path

import sqlglot
from pydbml import PyDBML
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

SCHEMA_DIR = Path(__file__).parent / ".schema" / "listening_activity"
CDM_PIPELINE = "listening_activity_cdm"
DIALECT = "duckdb"
MAX_ROWS = 200
WRITE_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Merge, exp.Command)
GROUPABLE = {"dimension", "time_dimension", "label"}


def load_cdm() -> dict[str, dict[str, str]]:
    """Return {table: {column: role}} from CDM.dbml."""
    cdm = {}
    for table in PyDBML((SCHEMA_DIR / "CDM.dbml").read_text()).tables:
        cdm[table.name] = {}
        for col in table.columns:
            note = str(col.note.text) if col.note else ""
            role = note.split("role:")[1].split(";")[0].strip() if "role:" in note else "unknown"
            cdm[table.name][col.name] = role
    return cdm


def load_ison_section(name: str) -> list[dict[str, str]]:
    """Return the rows of one tab-separated section of ontology.ison."""
    rows, header, inside = [], None, False
    for line in (SCHEMA_DIR / "ontology.ison").read_text().splitlines():
        if line.startswith(("nodes.", "edges.")):
            inside, header = line == name, None
        elif inside and line.strip():
            cells = line.split("\t")
            if header is None:
                header = cells
            else:
                rows.append(dict(zip(header, cells + [""] * (len(header) - len(cells)))))
    return rows


def check_sql(sql: str, cdm: dict[str, dict[str, str]]) -> list[str]:
    """Return the reasons to reject a SQL statement, or an empty list."""
    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except ParseError as error:
        return [f"SQL does not parse: {str(error).splitlines()[0]}"]
    if len(statements) != 1:
        return [f"Expected exactly 1 statement, got {len(statements)}"]
    tree = statements[0]
    if not isinstance(tree, exp.Query) or any(tree.find_all(*WRITE_NODES)):
        return ["Only read-only SELECT queries are allowed"]
    reasons = []
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.name not in cdm and table.name not in ctes:
            reasons.append(f"Unknown table '{table.name}': use only CDM tables {sorted(cdm)}")
    if any(isinstance(p, exp.Star) for p in tree.selects):
        reasons.append("SELECT * is not allowed: name the columns")
    limit = tree.args.get("limit")
    if limit is None:
        reasons.append(f"Add LIMIT (at most {MAX_ROWS}) to the outer query")
    elif not limit.expression.is_int or int(limit.expression.name) > MAX_ROWS:
        reasons.append(f"LIMIT must be a number of at most {MAX_ROWS}")
    if reasons:
        return reasons
    schema = {t: {c: "VARCHAR" for c in cols} for t, cols in cdm.items()}
    try:
        qualify(tree.copy(), schema=schema, dialect=DIALECT, validate_qualify_columns=True)
    except OptimizeError as error:
        reasons.append(f"Unknown or ambiguous column: {error}")
    return reasons


def check_plan(plan: dict, cdm: dict[str, dict[str, str]]) -> list[str]:
    """Return the reasons to reject an analysis plan, or an empty list."""
    required = ["question", "concepts", "metrics", "group_by", "filters", "assumptions"]
    reasons = [f"Plan is missing '{key}'" for key in required if key not in plan]
    if reasons:
        return reasons
    entities = {row["id"] for row in load_ison_section("nodes.Entity")}
    metrics = {row["name"] for row in load_ison_section("nodes.Metric")}
    reasons += [f"Unknown concept '{c}': use one of {sorted(entities)}" for c in plan["concepts"] if c not in entities]
    reasons += [f"Unknown metric '{m}': use one of {sorted(metrics)}" for m in plan["metrics"] if m not in metrics]
    for ref in plan["group_by"]:
        table, _, column = ref.partition(".")
        role = cdm.get(table, {}).get(column)
        if role is None:
            reasons.append(f"Unknown group_by column '{ref}': use table.column from CDM.dbml")
        elif role not in GROUPABLE:
            reasons.append(f"Cannot group by '{ref}': its role is {role}")
    return reasons


def context(cdm: dict[str, dict[str, str]]) -> str:
    """Return a compact text view of the CDM, metrics, and relationships."""
    lines = ["# CDM tables (column:role)"]
    lines += [f"{t}: " + ", ".join(f"{c}:{r}" for c, r in cols.items()) for t, cols in cdm.items()]
    lines.append("\n# Metrics (name | expression | table | filters | aliases)")
    for m in load_ison_section("nodes.Metric"):
        lines.append(f"{m['name']} | {m['expression']} | {m['table']} | {m['filters'] or '-'} | {m['aliases']}")
    lines.append("\n# Entities")
    lines += [f"{e['id']}: {e['assumption']}" for e in load_ison_section("nodes.Entity")]
    return "\n".join(lines)


def report(reasons: list[str]) -> int:
    """Print the verdict and return a process exit code."""
    if reasons:
        print("REJECTED\n" + "\n".join(f"- {r}" for r in reasons))
        return 1
    print("APPROVED")
    return 0


def hook(cdm: dict[str, dict[str, str]]) -> int:
    """Block execute_sql_query on the CDM unless the SQL passes the gate."""
    tool_input = json.load(sys.stdin).get("tool_input", {})
    if tool_input.get("pipeline_name") != CDM_PIPELINE:
        return 0
    reasons = check_sql(tool_input.get("sql_select_query", ""), cdm)
    if reasons:
        print("Gate rejected the SQL:\n" + "\n".join(f"- {r}" for r in reasons), file=sys.stderr)
        return 2
    return 0


SELF_TEST = [
    ("SELECT played_date, COUNT(play_sk) AS plays FROM fact_play GROUP BY 1 ORDER BY 1 LIMIT 50", True),
    ("SELECT a.artist_name, COUNT(p.play_sk) AS n FROM fact_play p JOIN bridge_track_artist b "
     "ON p.track_sk = b.track_sk JOIN dim_artist a ON b.artist_sk = a.artist_sk GROUP BY 1 LIMIT 10", True),
    ("WITH recent AS (SELECT track_sk FROM fact_play) SELECT COUNT(*) AS n FROM recent LIMIT 1", True),
    ("DELETE FROM fact_play", False),
    ("DROP TABLE dim_track", False),
    ("SELECT 1 LIMIT 1; DELETE FROM fact_play", False),
    ("SELECT played_at FROM plays LIMIT 10", False),
    ("SELECT * FROM fact_play LIMIT 10", False),
    ("SELECT played_at FROM fact_play", False),
    ("SELECT played_at FROM fact_play LIMIT 100000", False),
    ("SELECT genre FROM dim_artist LIMIT 10", False),
    ("SELEC played_at FROM fact_play", False),
]


def self_test(cdm: dict[str, dict[str, str]]) -> int:
    """Run the built-in SQL cases and print a summary."""
    failed = [sql for sql, ok in SELF_TEST if (not check_sql(sql, cdm)) != ok]
    for sql in failed:
        print(f"FAIL: {sql}")
    print(f"gate self-test: {len(SELF_TEST) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


def main() -> int:
    cdm = load_cdm()
    command = sys.argv[1] if len(sys.argv) > 1 else "--help"
    if command == "context":
        print(context(cdm))
        return 0
    if command == "check-sql":
        return report(check_sql(Path(sys.argv[2]).read_text(), cdm))
    if command == "check-plan":
        return report(check_plan(json.loads(Path(sys.argv[2]).read_text()), cdm))
    if command == "hook":
        return hook(cdm)
    if command == "--self-test":
        return self_test(cdm)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
