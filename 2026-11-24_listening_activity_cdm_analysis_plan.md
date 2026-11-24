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

## Data Gaps
Genre: Spotify returns no artist genres for Development Mode apps, so there is no genre chart.

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
