# Prompt: build the "My music history" dashboard

Paste this into Claude Code (or another agent with the AI Harness `data-exploration`
toolkit installed) after the CDM and the metrics exist. It runs `/explore-data` in bulk
mode and then `/build-notebook`.

---

```text
Use /explore-data on the pipeline listening_activity_cdm (dataset listening_activity;
DuckDB locally, the dltHub playground when deployed), bulk path: plan all charts in one analysis plan, then
run /build-notebook to create my_music_history.py.

GOAL
A dashboard of my music history. Long-history data first; plays last.

SECTIONS (in this order)
0. Header tiles (mo.stat): liked songs since <first added_at month>, artists in my
   library, saved albums, tracks added to playlists, oldest release year I like.
   Under the tiles, one sentence that defines "library" (see RULES).
1. How my library grew
   - Liked songs per month (bars) with library size as a line, independent y axes.
   - Tracks added to my playlists per quarter, stacked by playlist.
2. Who I love
   - Top 15 artists in my library: distinct songs that are liked OR in my playlists,
     stacked as "liked" / "only in my playlists", sorted by the total.
   - New artists per year (year of the first liked song per artist).
   - Table: top 3 artists of each year by songs liked that year, newest year first.
3. What era I live in
   - Liked songs by release decade.
   - Heatmap: year liked x release decade.
4. What Spotify sees
   - Spotify's long-term top 15 artists, with how many of their songs I liked.
   - Heatmap: top-artist overlap across short_term, medium_term, long_term.
   - Table: Spotify's long-term top 10 tracks, with a liked / not liked flag.
5. How my taste changed
   - Explicit share and singles share of what I liked, per year liked.
6. Recent listening (last section)
   - First a sentence with the exact plays date range (MIN/MAX played_at) and why it is
     short: Spotify keeps only the last 50 plays; history grows with each load.
   - Tiles: plays, listening minutes.
   - Top 10 artists recently, hour x weekday heatmap (UTC), top listening contexts.

RULES (learned the hard way)
- Connect with `from destinations import cdm_dataset; dataset = cdm_dataset()`. It
  attaches listening_activity_cdm with an explicit destination (duckdb on the local dev
  profile, playground on dltHub) and dataset; dltHub runs have no local pipeline state.
  Never write "playground" locally: it exists only on dltHub.
- Use the metric formulas from .schema/listening_activity/ontology.ison verbatim
  (plays, listening_minutes, saved_tracks, saved_albums, library_songs,
  forgotten_favorites). Use column roles from CDM.dbml: group by dimensions, sum measures.
- "Library" = liked songs (fact_saved_track) UNION tracks in playlists I own or
  collaborate on (fact_playlist_item). Say in the header that followed playlists are not
  included: Spotify returns no tracks for them. Never title a liked-songs-only chart
  "library".
- Count songs per artist with COUNT(DISTINCT track_sk) through bridge_track_artist; a
  song with two artists counts once for each artist.
- Break ties deterministically: ORDER BY <value> DESC, <name>.
- Decades: CAST(CAST(FLOOR(release_year / 10) * 10 AS INTEGER) AS VARCHAR) || 's'
  (without the INTEGER cast you get "1970.0s").
- Spotify's rankings: filter fact_top_item to the latest snapshot_date; short_term is
  about 4 weeks, medium_term about 6 months, long_term about 1 year.
- duration_ms is track length, not time listened: label minutes as an upper bound.
- Contexts: resolve context_uri (spotify:<type>:<id>) to playlist, album, or artist
  names; label unresolved playlists "A playlist not in my library" and a missing context
  "No context (search or queue)".
- Hours are UTC; say so.
- No genres, popularity, or audio features exist for Spotify Development Mode apps: list
  them under Data Gaps, do not chart them. Also list: real listening time and skips are
  only in Spotify's Extended streaming history export.

BUILD AND CHECK
- Run every SQL query against the CDM before writing it into the plan.
- Charts: aggregated queries only; every chart cell ends with `_chart` then `return`.
  Tables: mo.ui.table(df, selection=None). Tiles: mo.stat.
- Make sure pandas, numpy and altair are in pyproject.toml (uv add pandas numpy altair).
- Validate: uvx marimo check my_music_history.py, then
  uv run marimo export html my_music_history.py -o /tmp/report.html and confirm there
  are no cell errors (no "vnd.marimo+error" in the file).
- Add `import my_music_history` and "my_music_history" to __all__ in __deployment__.py.
```

---

**Expected result:** tiles, 12 charts, and 2 tables in 7 sections; `marimo check` clean;
0 cell errors in the export. Only the last section depends on plays.
