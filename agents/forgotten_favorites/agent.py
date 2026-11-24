"""Hook for the forgotten_favorites agent: loads candidate rows before the loop."""

from datetime import date
from typing import Any, Dict

import dlt
from dlt.hub.run import JobAbortedException

DESTINATION = "playground"
CANDIDATES_SQL = """
SELECT t.source_id AS track_id, t.track_name, COALESCE(a.artist_name, '?') AS artist_name,
       CAST(s.added_date AS VARCHAR) AS saved
FROM fact_saved_track s
JOIN dim_track t ON s.track_sk = t.track_sk
LEFT JOIN bridge_track_artist b ON b.track_sk = t.track_sk AND b.artist_position = 0
LEFT JOIN dim_artist a ON a.artist_sk = b.artist_sk
WHERE NOT EXISTS (
        SELECT 1 FROM fact_play p
        WHERE p.track_sk = s.track_sk AND p.played_at >= CURRENT_DATE - INTERVAL '30' DAY)
  AND NOT EXISTS (
        SELECT 1 FROM fact_top_item ti
        WHERE ti.track_sk = s.track_sk AND ti.time_range = 'short_term'
          AND ti.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item))
ORDER BY RANDOM()
LIMIT 60
"""


def render(rows: list) -> str:
    """Render candidate rows as a markdown table the model can copy ids from."""
    lines = ["| track_id | track | main artist | saved |", "|---|---|---|---|"]
    for track_id, name, artist, saved in rows:
        clean = str(name).replace("|", "/")
        lines.append(f"| {track_id} | {clean} | {str(artist).replace('|', '/')} | {saved} |")
    return "\n".join(lines)


def validate_input(inputs: Dict[str, Any]) -> Dict[str, Any]:
    rows = dlt.dataset(DESTINATION, "listening_activity")(CANDIDATES_SQL).fetchall()
    if not rows:
        raise JobAbortedException("No forgotten favorites this week", {"status": "aborted"})
    year, week, _ = date.today().isocalendar()
    return {**inputs, "week": f"{year}-W{week:02d}", "candidates": render(rows)}
