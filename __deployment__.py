"""ChatBI course — Spotify listening data, report app, and a weekly agent."""

from dlt.hub import run

import my_music_history
from listening_jobs import build_cdm, ingest

forgotten_favorites = run.agent(
    "agents/forgotten_favorites",
    name="forgotten_favorites",
    trigger="schedule:0 9 * * 1",
    require={"profile": "access"},
)

__all__ = [
    "ingest",
    "build_cdm",
    "my_music_history",
    "forgotten_favorites",
]
