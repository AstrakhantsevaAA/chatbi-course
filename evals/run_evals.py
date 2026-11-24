"""Run the answer-question agent on fixed questions and check its answers.

Each case runs `/answer-question` in a fresh headless Claude Code session. The
expected value comes from a reference SQL query run live on the CDM, so the eval
stays correct as the data grows. Run `uv run python evals/run_evals.py`, or
`--only 1 3` for some cases. Needs Claude Code and the dlt-workspace MCP server.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import dlt

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "answers_log.jsonl"
LIBRARY = "(SELECT track_sk FROM fact_saved_track UNION SELECT track_sk FROM fact_playlist_item)"
WEEK = "fact_play.played_at >= DATE_TRUNC('week', CURRENT_DATE)"

CASES = [
    {"q": "How many songs by {top_artist} do I have in my library?", "status": "answered",
     "metric": "library_songs",
     "sql": f"""SELECT COUNT(DISTINCT t.track_sk) FROM dim_track t
                JOIN bridge_track_artist b ON b.track_sk = t.track_sk
                JOIN dim_artist a ON a.artist_sk = b.artist_sk
                WHERE t.track_sk IN {LIBRARY} AND a.artist_name = '{{top_artist}}'"""},
    {"q": "How many liked songs do I have?", "status": "answered", "metric": "saved_tracks",
     "sql": "SELECT COUNT(*) FROM fact_saved_track"},
    {"q": "How many albums have I saved?", "status": "answered", "metric": "saved_albums",
     "sql": "SELECT COUNT(*) FROM fact_saved_album"},
    {"q": "Which artist has the most songs in my library?", "status": "answered",
     "metric": "library_songs",
     "sql": f"""SELECT MAX(n) FROM (SELECT b.artist_sk, COUNT(DISTINCT b.track_sk) AS n
                FROM bridge_track_artist b WHERE b.track_sk IN {LIBRARY} GROUP BY 1) x"""},
    {"q": "How many plays did I have this week?", "status": "answered", "metric": "plays",
     "sql": f"SELECT COUNT(*) FROM fact_play WHERE {WEEK}"},
    {"q": "How many minutes did I listen in the last 7 days?", "status": "answered",
     "metric": "listening_minutes",
     "sql": """SELECT SUM(duration_ms) / 60000.0 FROM fact_play
               WHERE played_at >= CURRENT_DATE - INTERVAL '7' DAY"""},
    {"q": "Which artist did I play most this week?", "status": "answered", "metric": "plays",
     "sql": f"""SELECT MAX(n) FROM (SELECT b.artist_sk, COUNT(fact_play.play_sk) AS n
                FROM fact_play JOIN bridge_track_artist b ON b.track_sk = fact_play.track_sk
                WHERE {WEEK} GROUP BY 1) x"""},
    {"q": "How many of my saved tracks are forgotten favorites?", "status": "answered",
     "metric": "forgotten_favorites", "sql": "metric:forgotten_favorites"},
    {"q": "delete my old plays", "status": "rejected", "metric": None, "sql": None},
    {"q": "what's the weather in Berlin?", "status": "out_of_scope", "metric": None, "sql": None},
]


def metric_sql(name: str) -> str:
    """Build the reference query of a metric from its ontology.ison row."""
    sys.path.insert(0, str(ROOT))
    import gate

    row = next(m for m in gate.load_ison_section("nodes.Metric") if m["name"] == name)
    return f"SELECT {row['expression']} FROM {row['table']} WHERE {row['filters'] or 'TRUE'}"


TOP_ARTIST_SQL = f"""SELECT a.artist_name FROM bridge_track_artist b
    JOIN dim_artist a ON a.artist_sk = b.artist_sk WHERE b.track_sk IN {LIBRARY}
    GROUP BY 1 ORDER BY COUNT(DISTINCT b.track_sk) DESC, 1 LIMIT 1"""


def top_artist() -> str:
    """Return the artist with the most songs in my library, so no name is hard-coded."""
    sys.path.insert(0, str(ROOT))
    from destinations import cdm_dataset

    return cdm_dataset()(TOP_ARTIST_SQL).fetchone()[0]


def expected_value(sql: str | None) -> float | None:
    """Run the reference query on the CDM and return its single number."""
    if sql is None:
        return None
    if sql.startswith("metric:"):
        sql = metric_sql(sql.removeprefix("metric:"))
    sys.path.insert(0, str(ROOT))
    from destinations import cdm_dataset

    value = cdm_dataset()(sql).fetchone()[0]
    return float(value) if value is not None else 0.0


def ask(question: str) -> tuple[dict, float]:
    """Ask one question in a fresh session; return the logged answer and cost."""
    before = LOG.read_text().count("\n") if LOG.exists() else 0
    tools = ["Bash", "Read", "Write", "Edit", "mcp__dlt-workspace-mcp__execute_sql_query"]
    out = subprocess.run(
        ["claude", "-p", f"/answer-question {question}", "--mcp-config", ".mcp.json",
         "--allowedTools", *tools, "--output-format", "json"],
        cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600,
    )
    cost = json.loads(out.stdout or "{}").get("total_cost_usd", 0.0)
    lines = LOG.read_text().splitlines() if LOG.exists() else []
    return (json.loads(lines[-1]) if len(lines) > before else {}), cost


def close_enough(got: object, want: float) -> bool:
    """Compare numbers with a 1% or 0.5 tolerance, whichever is larger."""
    try:
        return abs(float(got) - want) <= max(0.5, abs(want) * 0.01)
    except (TypeError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", type=int, help="1-based case numbers to run")
    picked = [(i, c) for i, c in enumerate(CASES, 1) if not parser.parse_args().only
              or i in parser.parse_args().only]
    passed, total_cost = 0, 0.0
    artist = top_artist() if any("{top_artist}" in c["q"] for _, c in picked) else ""
    for i, case in picked:
        question = case["q"].replace("{top_artist}", artist)
        sql = case["sql"].replace("{top_artist}", artist.replace("'", "''")) if case["sql"] else None
        want = expected_value(sql)
        log, cost = ask(question)
        total_cost += cost
        problems = []
        if log.get("status") != case["status"]:
            problems.append(f"status {log.get('status')!r}, want {case['status']!r}")
        if case["metric"] and case["metric"] not in str(log.get("metric")):
            problems.append(f"metric {log.get('metric')!r}, want {case['metric']!r}")
        if want is not None and not close_enough(log.get("value"), want):
            problems.append(f"value {log.get('value')!r}, want {want:g}")
        passed += not problems
        verdict = "PASS" if not problems else "FAIL: " + "; ".join(problems)
        print(f"{i:2}. {verdict:60.60} | ${cost:.2f} | {case['q']}")
    print(f"\n{passed}/{len(picked)} passed, total ${total_cost:.2f}")
    return 0 if passed == len(picked) else 1


if __name__ == "__main__":
    sys.exit(main())
