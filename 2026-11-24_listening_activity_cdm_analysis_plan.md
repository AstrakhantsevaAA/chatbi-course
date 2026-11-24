# Analysis Plan: listening_activity_cdm

## Connection
pipeline: listening_activity_cdm
dataset: listening_activity
destination: duckdb

## Profile Summary
| table | rows | key columns | notes |
|-------|------|-------------|-------|
| fact_play | 50 | played_at, track_sk, context_type, duration_ms | temporal: played_at; history starts at first load |
| fact_saved_track | 377 | track_sk, added_at | temporal: added_at |
| fact_top_item | 272 | snapshot_date, item_type, time_range, rank | one snapshot per load day |
| dim_artist | 301 | artist_name | no genres (Spotify Development Mode) |
| bridge_track_artist | 829 | track_sk, artist_sk | many-to-many track to artist |

Charts reuse the metric formulas in `.schema/listening_activity/ontology.ison`, so the report and the agent agree.

## Questions
1. [x] How much do I listen each day? → Chart 1
2. [x] Which artists do I play most? → Chart 2
3. [x] Do I listen from playlists, albums, or artist pages? → Chart 3
4. [x] How has my saved library grown? → Chart 4
5. [x] How many saved tracks have I forgotten? → Chart 5
6. [x] How do my long-term top artists rank now? → Chart 6

7. [x] At what hours and on which days do I listen? → Chart 7
8. [x] Which playlists, albums, and artist pages do I play from? → Chart 8
9. [x] How old is the music I play and save? → Chart 9
10. [x] Do I save music when it comes out, or years later? → Chart 10
11. [x] How much of my listening goes to my top artists? → Chart 11
12. [x] Do I listen to singles or albums? → Chart 12
13. [x] How much do my top artists overlap across time ranges? → Chart 13
14. [x] Which artists are new in my top, and which faded? → Chart 14
15. [x] How have my playlists grown over time? → Chart 15

## Data Gaps
Genre: Spotify returns no artist genres for Development Mode apps, so there is no genre chart.
Playlist names for plays from playlists I do not follow: needs GET /playlists/{id}, not loaded.
Real listening time and skips: only in Spotify's Extended streaming history export.

## Chart 1: Listening minutes per day
question: How much do I listen each day?
type: line
x: fact_play.played_date (daily)
y: listening_minutes metric
source: fact_play

```sql
SELECT played_date AS day, SUM(duration_ms) / 60000.0 AS listening_minutes, COUNT(play_sk) AS plays
FROM fact_play GROUP BY 1 ORDER BY 1
```

```altair
alt.Chart(df).mark_line(point=True).encode(
    x=alt.X("day:T", title="Day"),
    y=alt.Y("listening_minutes:Q", title="Listening minutes"),
    tooltip=["day:T", alt.Tooltip("listening_minutes:Q", format=".0f"), "plays:Q"]
).properties(title="Listening minutes per day")
```

## Chart 2: Top 10 artists by plays
question: Which artists do I play most?
type: bar
x: dim_artist.artist_name
y: plays metric
source: fact_play + bridge_track_artist + dim_artist

```sql
SELECT a.artist_name, COUNT(p.play_sk) AS plays
FROM fact_play p
JOIN bridge_track_artist b ON p.track_sk = b.track_sk
JOIN dim_artist a ON b.artist_sk = a.artist_sk
GROUP BY 1 ORDER BY 2 DESC LIMIT 10
```

```altair
alt.Chart(df).mark_bar().encode(
    x=alt.X("plays:Q", title="Plays"),
    y=alt.Y("artist_name:N", sort="-x", title=None),
    tooltip=["artist_name:N", "plays:Q"]
).properties(title="Top 10 artists by plays")
```

## Chart 3: Where my plays come from
question: Do I listen from playlists, albums, or artist pages?
type: bar
x: fact_play.context_type
y: plays metric
source: fact_play

```sql
SELECT context_type, COUNT(play_sk) AS plays FROM fact_play GROUP BY 1 ORDER BY 2 DESC
```

```altair
alt.Chart(df).mark_bar().encode(
    x=alt.X("context_type:N", sort="-y", title="Context"),
    y=alt.Y("plays:Q", title="Plays"),
    tooltip=["context_type:N", "plays:Q"]
).properties(title="Where my plays come from")
```

## Chart 4: Library growth
question: How has my saved library grown?
type: line
x: fact_saved_track.added_at (monthly)
y: running total of saved_tracks
source: fact_saved_track

```sql
SELECT DATE_TRUNC('month', added_at) AS month, COUNT(saved_track_sk) AS saved,
       SUM(COUNT(saved_track_sk)) OVER (ORDER BY DATE_TRUNC('month', added_at)) AS total_saved
FROM fact_saved_track GROUP BY 1 ORDER BY 1
```

```altair
alt.Chart(df).mark_area(opacity=0.6).encode(
    x=alt.X("month:T", title="Month"),
    y=alt.Y("total_saved:Q", title="Saved tracks (running total)"),
    tooltip=["month:T", "saved:Q", "total_saved:Q"]
).properties(title="Library growth")
```

## Chart 5: Forgotten favorites
question: How many saved tracks have I forgotten?
type: bar
x: forgotten_favorites filter (forgotten vs still in rotation)
y: saved_tracks metric
source: fact_saved_track

```sql
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM fact_play p WHERE p.track_sk = s.track_sk AND p.played_at >= CURRENT_DATE - INTERVAL '30' DAY) AND NOT EXISTS (SELECT 1 FROM fact_top_item t WHERE t.track_sk = s.track_sk AND t.time_range = 'short_term' AND t.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item)) THEN 'forgotten' ELSE 'still in rotation' END AS status,
       COUNT(s.saved_track_sk) AS saved_tracks
FROM fact_saved_track s GROUP BY 1
```

```altair
alt.Chart(df).mark_bar().encode(
    x=alt.X("saved_tracks:Q", title="Saved tracks"),
    y=alt.Y("status:N", title=None),
    color=alt.Color("status:N", legend=None),
    tooltip=["status:N", "saved_tracks:Q"]
).properties(title="Forgotten favorites vs tracks still in rotation")
```

## Chart 6: Taste shift
question: How do my long-term top artists rank now?
type: dot plot
x: time_range rank per artist
y: rank (1 = top)
source: fact_top_item + dim_artist

```sql
SELECT a.artist_name,
       MAX(CASE WHEN t.time_range = 'long_term' THEN t.rank END) AS long_term_rank,
       MAX(CASE WHEN t.time_range = 'medium_term' THEN t.rank END) AS medium_term_rank,
       MAX(CASE WHEN t.time_range = 'short_term' THEN t.rank END) AS short_term_rank
FROM fact_top_item t JOIN dim_artist a ON t.artist_sk = a.artist_sk
WHERE t.item_type = 'artists' AND t.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item)
GROUP BY 1
HAVING MAX(CASE WHEN t.time_range = 'long_term' THEN t.rank END) <= 10
ORDER BY long_term_rank
```

```altair
alt.Chart(df).transform_fold(
    ["long_term_rank", "medium_term_rank", "short_term_rank"], as_=["time_range", "rank"]
).mark_point(filled=True, size=90).encode(
    x=alt.X("rank:Q", scale=alt.Scale(reverse=True), title="Rank (1 = top)"),
    y=alt.Y("artist_name:N", sort=alt.EncodingSortField("long_term_rank"), title=None),
    color=alt.Color("time_range:N", title="Time range"),
    tooltip=["artist_name:N", "time_range:N", "rank:Q"]
).properties(title="Top 10 long-term artists: rank by time range")
```
## Chart 7: When I listen
question: At what hours and on which days do I listen?
type: heatmap
x: hour (UTC) × weekday
y: plays metric
source: fact_play

```sql
SELECT ISODOW(played_at) AS weekday_no, DAYNAME(played_at) AS weekday,
       EXTRACT(HOUR FROM played_at) AS hour_utc, COUNT(play_sk) AS plays
FROM fact_play GROUP BY 1, 2, 3 ORDER BY 1, 3
```

```altair
alt.Chart(df).mark_rect().encode(
    x=alt.X("hour_utc:O", title="Hour (UTC)"),
    y=alt.Y("weekday:N", sort=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], title=None),
    color=alt.Color("plays:Q", title="Plays"),
    tooltip=["weekday:N", "hour_utc:O", "plays:Q"]
).properties(title="When I listen")
```

## Chart 8: Top listening contexts
question: Which playlists, albums, and artist pages do I play from?
type: bar
x: context name
y: plays metric
source: fact_play + dim_playlist / dim_album / dim_artist

```sql
SELECT p.context_type,
       COALESCE(pl.playlist_name, al.album_name, ar.artist_name,
                CASE p.context_type WHEN 'playlist' THEN 'A playlist not in my library'
                     WHEN 'UNKNOWN' THEN 'No context (search or queue)' ELSE 'Other' END) AS context_name,
       COUNT(p.play_sk) AS plays
FROM fact_play p
LEFT JOIN dim_playlist pl ON p.context_type = 'playlist' AND pl.source_id = SPLIT_PART(p.context_uri, ':', 3)
LEFT JOIN dim_album al ON p.context_type = 'album' AND al.source_id = SPLIT_PART(p.context_uri, ':', 3)
LEFT JOIN dim_artist ar ON p.context_type = 'artist' AND ar.source_id = SPLIT_PART(p.context_uri, ':', 3)
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10
```

```altair
alt.Chart(df).mark_bar().encode(
    x=alt.X("plays:Q", title="Plays"),
    y=alt.Y("context_name:N", sort="-x", title=None),
    color=alt.Color("context_type:N", title="Context"),
    tooltip=["context_name:N", "context_type:N", "plays:Q"]
).properties(title="Top listening contexts")
```

## Chart 9: Release years
question: How old is the music I play and save?
type: bar
x: dim_album.release_year
y: count of tracks
source: fact_play, fact_saved_track + dim_album

```sql
SELECT 'plays' AS source, a.release_year, COUNT(p.play_sk) AS tracks
FROM fact_play p JOIN dim_album a ON p.album_sk = a.album_sk
WHERE a.release_year IS NOT NULL GROUP BY 1, 2
UNION ALL
SELECT 'saved tracks', a.release_year, COUNT(s.saved_track_sk)
FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk
JOIN dim_album a ON t.album_sk = a.album_sk
WHERE a.release_year IS NOT NULL GROUP BY 1, 2
ORDER BY 2
```

```altair
alt.Chart(df).mark_bar(opacity=0.8).encode(
    x=alt.X("release_year:O", title="Release year"),
    y=alt.Y("tracks:Q", title="Tracks"),
    color=alt.Color("source:N", title=None),
    xOffset="source:N",
    tooltip=["source:N", "release_year:O", "tracks:Q"]
).properties(title="Release years: what I play vs what I save")
```

## Chart 10: New music or old?
question: Do I save music when it comes out, or years later?
type: bar
x: years from release to save (bucket)
y: saved_tracks metric
source: fact_saved_track + dim_album

```sql
SELECT CASE
         WHEN EXTRACT(YEAR FROM s.added_at) - a.release_year <= 0 THEN '1 · release year'
         WHEN EXTRACT(YEAR FROM s.added_at) - a.release_year <= 2 THEN '2 · 1–2 years later'
         WHEN EXTRACT(YEAR FROM s.added_at) - a.release_year <= 5 THEN '3 · 3–5 years later'
         WHEN EXTRACT(YEAR FROM s.added_at) - a.release_year <= 10 THEN '4 · 6–10 years later'
         ELSE '5 · 10+ years later' END AS saved_when,
       COUNT(s.saved_track_sk) AS saved_tracks
FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk
JOIN dim_album a ON t.album_sk = a.album_sk
WHERE a.release_year IS NOT NULL GROUP BY 1 ORDER BY 1
```

```altair
alt.Chart(df).mark_bar().encode(
    x=alt.X("saved_when:N", title="When I saved it"),
    y=alt.Y("saved_tracks:Q", title="Saved tracks"),
    tooltip=["saved_when:N", "saved_tracks:Q"]
).properties(title="When I save music, relative to its release")
```

## Chart 11: Artist concentration
question: How much of my listening goes to my top artists?
type: line
x: artist rank
y: cumulative share of plays
source: fact_play + bridge_track_artist + dim_artist

```sql
WITH by_artist AS (
  SELECT a.artist_name, COUNT(p.play_sk) AS plays
  FROM fact_play p JOIN bridge_track_artist b ON p.track_sk = b.track_sk
  JOIN dim_artist a ON b.artist_sk = a.artist_sk GROUP BY 1)
SELECT artist_name, plays,
       ROW_NUMBER() OVER (ORDER BY plays DESC, artist_name) AS artist_rank,
       SUM(plays) OVER (ORDER BY plays DESC, artist_name) * 1.0 / SUM(plays) OVER () AS cumulative_share
FROM by_artist ORDER BY artist_rank
```

```altair
alt.Chart(df).mark_line(point=True).encode(
    x=alt.X("artist_rank:Q", title="Artist rank"),
    y=alt.Y("cumulative_share:Q", axis=alt.Axis(format="%"), title="Share of plays (cumulative)"),
    tooltip=["artist_rank:Q", "artist_name:N", "plays:Q", alt.Tooltip("cumulative_share:Q", format=".0%")]
).properties(title="Artist concentration")
```

## Chart 12: Singles vs albums
question: Do I listen to singles or albums?
type: normalized bar
x: dim_album.album_type
y: share of tracks
source: fact_play, fact_saved_track + dim_album

```sql
SELECT 'plays' AS source, a.album_type, COUNT(p.play_sk) AS tracks
FROM fact_play p JOIN dim_album a ON p.album_sk = a.album_sk GROUP BY 1, 2
UNION ALL
SELECT 'saved tracks', a.album_type, COUNT(s.saved_track_sk)
FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk
JOIN dim_album a ON t.album_sk = a.album_sk GROUP BY 1, 2
```

```altair
alt.Chart(df).mark_bar().encode(
    x=alt.X("tracks:Q", stack="normalize", axis=alt.Axis(format="%"), title="Share"),
    y=alt.Y("source:N", title=None),
    color=alt.Color("album_type:N", title="Release type"),
    tooltip=["source:N", "album_type:N", "tracks:Q"]
).properties(title="Singles vs albums")
```

## Chart 13: Taste stability
question: How much do my top artists overlap across time ranges?
type: heatmap
x: time range × time range
y: overlap share
source: fact_top_item

```sql
WITH latest AS (
  SELECT time_range, artist_sk FROM fact_top_item
  WHERE item_type = 'artists' AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item))
SELECT x.time_range AS range_a, y.time_range AS range_b,
       COUNT(DISTINCT CASE WHEN x.artist_sk = y.artist_sk THEN x.artist_sk END) * 1.0
         / COUNT(DISTINCT x.artist_sk) AS overlap
FROM latest x CROSS JOIN latest y GROUP BY 1, 2 ORDER BY 1, 2
```

```altair
alt.Chart(df).mark_rect().encode(
    x=alt.X("range_b:N", sort=["short_term", "medium_term", "long_term"], title="Also in"),
    y=alt.Y("range_a:N", sort=["short_term", "medium_term", "long_term"], title="Top artists of"),
    color=alt.Color("overlap:Q", scale=alt.Scale(domain=[0, 1]), title="Overlap"),
    tooltip=["range_a:N", "range_b:N", alt.Tooltip("overlap:Q", format=".0%")]
).properties(title="Taste stability: top-artist overlap")
```

## Chart 14: New and faded artists
question: Which artists are new in my top, and which faded?
type: bar
x: artist
y: rank (1 = top)
source: fact_top_item + dim_artist

```sql
WITH latest AS (
  SELECT t.time_range, t.rank, a.artist_name FROM fact_top_item t
  JOIN dim_artist a ON t.artist_sk = a.artist_sk
  WHERE t.item_type = 'artists' AND t.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item))
SELECT 'new in my top' AS movement, s.artist_name, s.rank
FROM latest s WHERE s.time_range = 'short_term' AND s.rank <= 15
  AND s.artist_name NOT IN (SELECT artist_name FROM latest WHERE time_range = 'long_term')
UNION ALL
SELECT 'faded', l.artist_name, l.rank
FROM latest l WHERE l.time_range = 'long_term' AND l.rank <= 15
  AND l.artist_name NOT IN (SELECT artist_name FROM latest WHERE time_range = 'short_term')
ORDER BY 1, 3
```

```altair
alt.Chart(df).mark_bar().encode(
    x=alt.X("rank:Q", scale=alt.Scale(reverse=True), title="Rank in its time range (1 = top)"),
    y=alt.Y("artist_name:N", sort=alt.EncodingSortField("rank"), title=None),
    color=alt.Color("movement:N", title=None),
    row=alt.Row("movement:N", title=None),
    tooltip=["movement:N", "artist_name:N", "rank:Q"]
).resolve_scale(y="independent").properties(title="New in my top (short_term) and faded (long_term)")
```

## Chart 15: Playlist growth
question: How have my playlists grown over time?
type: line
x: month
y: running total of tracks
source: fact_playlist_item + dim_playlist

```sql
SELECT pl.playlist_name, DATE_TRUNC('month', i.added_at) AS month,
       SUM(COUNT(i.playlist_item_sk)) OVER (PARTITION BY pl.playlist_name ORDER BY DATE_TRUNC('month', i.added_at)) AS total_tracks
FROM fact_playlist_item i JOIN dim_playlist pl ON i.playlist_sk = pl.playlist_sk
WHERE i.added_at IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2
```

```altair
alt.Chart(df).mark_line(point=True).encode(
    x=alt.X("month:T", title="Month"),
    y=alt.Y("total_tracks:Q", title="Tracks (running total)"),
    color=alt.Color("playlist_name:N", title="Playlist"),
    tooltip=["playlist_name:N", "month:T", "total_tracks:Q"]
).properties(title="Playlist growth")
```

## Diversity tiles
question: How varied is my listening?
type: stat tiles
source: fact_play + bridge_track_artist + dim_track

```sql
WITH by_artist AS (
  SELECT b.artist_sk, COUNT(p.play_sk) AS plays FROM fact_play p
  JOIN bridge_track_artist b ON p.track_sk = b.track_sk GROUP BY 1)
SELECT (SELECT COUNT(*) FROM by_artist) AS distinct_artists,
       (SELECT MAX(plays) * 1.0 / SUM(plays) FROM by_artist) AS top_artist_share,
       (SELECT AVG(CASE WHEN n > 1 THEN 1.0 ELSE 0 END) FROM
          (SELECT track_sk, COUNT(*) AS n FROM bridge_track_artist GROUP BY 1) c) AS collab_share,
       (SELECT AVG(CASE WHEN t.is_explicit THEN 1.0 ELSE 0 END) FROM fact_play p
          JOIN dim_track t ON p.track_sk = t.track_sk) AS explicit_share
```

