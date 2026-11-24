"""Listening report: a dltHub data app over the listening_activity CDM.

Run `uv run marimo run listening_activity_cdm_dashboard.py` after the CDM is built.
Built with the AI Harness data-exploration toolkit from the analysis plan.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import dlt

    return alt, dlt, mo


@app.cell
def _(dlt):
    pipeline = dlt.attach("listening_activity_cdm", destination="playground", dataset_name="listening_activity")
    dataset = pipeline.dataset()
    return (dataset,)


@app.cell
def _(dataset, mo):
    _kpi = dataset("""
        SELECT
            (SELECT COUNT(play_sk) FROM fact_play) AS plays,
            (SELECT SUM(duration_ms) / 60000.0 FROM fact_play) AS listening_minutes,
            (SELECT COUNT(saved_track_sk) FROM fact_saved_track) AS saved_tracks,
            (SELECT MIN(played_at) FROM fact_play) AS data_from,
            (SELECT MAX(played_at) FROM fact_play) AS data_through
    """).df().iloc[0]
    mo.vstack([
        mo.md("# My listening report"),
        mo.hstack([
            mo.stat(value=f"{_kpi.plays:,}", label="Plays"),
            mo.stat(value=f"{_kpi.listening_minutes:,.0f}", label="Listening minutes"),
            mo.stat(value=f"{_kpi.saved_tracks:,}", label="Saved tracks"),
        ], justify="start"),
        mo.md(f"Play history: **{_kpi.data_from:%Y-%m-%d}** to **{_kpi.data_through:%Y-%m-%d}**. "
              "It grows with every scheduled load. Hours are in UTC."),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## How much I listen
    """)
    return


@app.cell
def _(dataset):
    df_chart1 = dataset("""
        SELECT played_date AS day, SUM(duration_ms) / 60000.0 AS listening_minutes, COUNT(play_sk) AS plays
        FROM fact_play GROUP BY 1 ORDER BY 1
    """).df()
    return (df_chart1,)


@app.cell
def _(alt, df_chart1):
    _chart = (
        alt.Chart(df_chart1).mark_line(point=True).encode(
            x=alt.X("day:T", title="Day"),
            y=alt.Y("listening_minutes:Q", title="Listening minutes"),
            tooltip=["day:T", alt.Tooltip("listening_minutes:Q", format=".0f"), "plays:Q"]
        ).properties(title="Listening minutes per day")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart2 = dataset("""
        SELECT a.artist_name, COUNT(p.play_sk) AS plays
        FROM fact_play p
        JOIN bridge_track_artist b ON p.track_sk = b.track_sk
        JOIN dim_artist a ON b.artist_sk = a.artist_sk
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """).df()
    return (df_chart2,)


@app.cell
def _(alt, df_chart2):
    _chart = (
        alt.Chart(df_chart2).mark_bar().encode(
            x=alt.X("plays:Q", title="Plays"),
            y=alt.Y("artist_name:N", sort="-x", title=None),
            tooltip=["artist_name:N", "plays:Q"]
        ).properties(title="Top 10 artists by plays")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart3 = dataset("""
        SELECT context_type, COUNT(play_sk) AS plays FROM fact_play GROUP BY 1 ORDER BY 2 DESC
    """).df()
    return (df_chart3,)


@app.cell
def _(alt, df_chart3):
    _chart = (
        alt.Chart(df_chart3).mark_bar().encode(
            x=alt.X("context_type:N", sort="-y", title="Context"),
            y=alt.Y("plays:Q", title="Plays"),
            tooltip=["context_type:N", "plays:Q"]
        ).properties(title="Where my plays come from")
    )
    _chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## When I listen
    """)
    return


@app.cell
def _(dataset):
    df_chart7 = dataset("""
        SELECT ISODOW(played_at) AS weekday_no, DAYNAME(played_at) AS weekday,
               EXTRACT(HOUR FROM played_at) AS hour_utc, COUNT(play_sk) AS plays
        FROM fact_play GROUP BY 1, 2, 3 ORDER BY 1, 3
    """).df()
    return (df_chart7,)


@app.cell
def _(alt, df_chart7):
    _chart = (
        alt.Chart(df_chart7).mark_rect().encode(
            x=alt.X("hour_utc:O", title="Hour (UTC)"),
            y=alt.Y("weekday:N", sort=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], title=None),
            color=alt.Color("plays:Q", title="Plays"),
            tooltip=["weekday:N", "hour_utc:O", "plays:Q"]
        ).properties(title="When I listen")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart8 = dataset("""
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
    """).df()
    return (df_chart8,)


@app.cell
def _(alt, df_chart8):
    _chart = (
        alt.Chart(df_chart8).mark_bar().encode(
            x=alt.X("plays:Q", title="Plays"),
            y=alt.Y("context_name:N", sort="-x", title=None),
            color=alt.Color("context_type:N", title="Context"),
            tooltip=["context_name:N", "context_type:N", "plays:Q"]
        ).properties(title="Top listening contexts")
    )
    _chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## What era I live in
    """)
    return


@app.cell
def _(dataset):
    df_chart9 = dataset("""
        SELECT 'plays' AS source, a.release_year, COUNT(p.play_sk) AS tracks
        FROM fact_play p JOIN dim_album a ON p.album_sk = a.album_sk
        WHERE a.release_year IS NOT NULL GROUP BY 1, 2
        UNION ALL
        SELECT 'saved tracks', a.release_year, COUNT(s.saved_track_sk)
        FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk
        JOIN dim_album a ON t.album_sk = a.album_sk
        WHERE a.release_year IS NOT NULL GROUP BY 1, 2
        ORDER BY 2
    """).df()
    return (df_chart9,)


@app.cell
def _(alt, df_chart9):
    _chart = (
        alt.Chart(df_chart9).mark_bar(opacity=0.8).encode(
            x=alt.X("release_year:O", title="Release year"),
            y=alt.Y("tracks:Q", title="Tracks"),
            color=alt.Color("source:N", title=None),
            xOffset="source:N",
            tooltip=["source:N", "release_year:O", "tracks:Q"]
        ).properties(title="Release years: what I play vs what I save")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart10 = dataset("""
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
    """).df()
    return (df_chart10,)


@app.cell
def _(alt, df_chart10):
    _chart = (
        alt.Chart(df_chart10).mark_bar().encode(
            x=alt.X("saved_when:N", title="When I saved it"),
            y=alt.Y("saved_tracks:Q", title="Saved tracks"),
            tooltip=["saved_when:N", "saved_tracks:Q"]
        ).properties(title="When I save music, relative to its release")
    )
    _chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## How varied I am
    """)
    return


@app.cell
def _(dataset, mo):
    _div = dataset("""
        WITH by_artist AS (
          SELECT b.artist_sk, COUNT(p.play_sk) AS plays FROM fact_play p
          JOIN bridge_track_artist b ON p.track_sk = b.track_sk GROUP BY 1)
        SELECT (SELECT COUNT(*) FROM by_artist) AS distinct_artists,
               (SELECT MAX(plays) * 1.0 / SUM(plays) FROM by_artist) AS top_artist_share,
               (SELECT AVG(CASE WHEN n > 1 THEN 1.0 ELSE 0 END) FROM
                  (SELECT track_sk, COUNT(*) AS n FROM bridge_track_artist GROUP BY 1) c) AS collab_share,
               (SELECT AVG(CASE WHEN t.is_explicit THEN 1.0 ELSE 0 END) FROM fact_play p
                  JOIN dim_track t ON p.track_sk = t.track_sk) AS explicit_share
    """).df().iloc[0]
    mo.hstack([
        mo.stat(value=f"{_div.distinct_artists:,}", label="Artists played"),
        mo.stat(value=f"{_div.top_artist_share:.0%}", label="Plays by my top artist"),
        mo.stat(value=f"{_div.collab_share:.0%}", label="Tracks with 2+ artists"),
        mo.stat(value=f"{_div.explicit_share:.0%}", label="Explicit plays"),
    ], justify="start")
    return


@app.cell
def _(dataset):
    df_chart11 = dataset("""
        WITH by_artist AS (
          SELECT a.artist_name, COUNT(p.play_sk) AS plays
          FROM fact_play p JOIN bridge_track_artist b ON p.track_sk = b.track_sk
          JOIN dim_artist a ON b.artist_sk = a.artist_sk GROUP BY 1)
        SELECT artist_name, plays,
               ROW_NUMBER() OVER (ORDER BY plays DESC, artist_name) AS artist_rank,
               SUM(plays) OVER (ORDER BY plays DESC, artist_name) * 1.0 / SUM(plays) OVER () AS cumulative_share
        FROM by_artist ORDER BY artist_rank
    """).df()
    return (df_chart11,)


@app.cell
def _(alt, df_chart11):
    _chart = (
        alt.Chart(df_chart11).mark_line(point=True).encode(
            x=alt.X("artist_rank:Q", title="Artist rank"),
            y=alt.Y("cumulative_share:Q", axis=alt.Axis(format="%"), title="Share of plays (cumulative)"),
            tooltip=["artist_rank:Q", "artist_name:N", "plays:Q", alt.Tooltip("cumulative_share:Q", format=".0%")]
        ).properties(title="Artist concentration")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart12 = dataset("""
        SELECT 'plays' AS source, a.album_type, COUNT(p.play_sk) AS tracks
        FROM fact_play p JOIN dim_album a ON p.album_sk = a.album_sk GROUP BY 1, 2
        UNION ALL
        SELECT 'saved tracks', a.album_type, COUNT(s.saved_track_sk)
        FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk
        JOIN dim_album a ON t.album_sk = a.album_sk GROUP BY 1, 2
    """).df()
    return (df_chart12,)


@app.cell
def _(alt, df_chart12):
    _chart = (
        alt.Chart(df_chart12).mark_bar().encode(
            x=alt.X("tracks:Q", stack="normalize", axis=alt.Axis(format="%"), title="Share"),
            y=alt.Y("source:N", title=None),
            color=alt.Color("album_type:N", title="Release type"),
            tooltip=["source:N", "album_type:N", "tracks:Q"]
        ).properties(title="Singles vs albums")
    )
    _chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## My library
    """)
    return


@app.cell
def _(dataset, mo):
    _lib = dataset("""
        SELECT
            (SELECT COUNT(saved_track_sk) FROM fact_saved_track) AS liked_songs,
            (SELECT COUNT(saved_album_sk) FROM fact_saved_album) AS saved_albums,
            (SELECT COUNT(playlist_sk) FROM dim_playlist WHERE is_mine) AS my_playlists,
            (SELECT COUNT(playlist_sk) FROM dim_playlist WHERE NOT is_mine) AS followed_playlists,
            (SELECT SUM(items_total) FROM dim_playlist WHERE is_mine) AS tracks_in_my_playlists
    """).df().iloc[0]
    mo.hstack([
        mo.stat(value=f"{_lib.liked_songs:,}", label="Liked songs"),
        mo.stat(value=f"{_lib.saved_albums:,}", label="Saved albums"),
        mo.stat(value=f"{_lib.my_playlists:,}", label="My playlists"),
        mo.stat(value=f"{_lib.followed_playlists:,}", label="Followed playlists"),
        mo.stat(value=f"{_lib.tracks_in_my_playlists:,}", label="Tracks in my playlists"),
    ], justify="start")
    return


@app.cell
def _(dataset):
    df_chart17 = dataset("""
        SELECT a.artist_name, COUNT(f.saved_album_sk) AS saved_albums
        FROM fact_saved_album f JOIN dim_artist a ON f.artist_sk = a.artist_sk
        GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10
    """).df()
    return (df_chart17,)


@app.cell
def _(alt, df_chart17):
    _chart = (
        alt.Chart(df_chart17).mark_bar().encode(
            x=alt.X("saved_albums:Q", title="Saved albums"),
            y=alt.Y("artist_name:N", sort="-x", title=None),
            tooltip=["artist_name:N", "saved_albums:Q"]
        ).properties(title="Top 10 artists in my saved albums")
    )
    _chart
    return


@app.cell
def _(dataset, mo):
    _recent = dataset("""
        SELECT al.album_name AS album, ar.artist_name AS artist, al.release_year,
               f.added_date AS saved_on
        FROM fact_saved_album f
        JOIN dim_album al ON f.album_sk = al.album_sk
        JOIN dim_artist ar ON f.artist_sk = ar.artist_sk
        ORDER BY f.added_at DESC LIMIT 10
    """).df()
    mo.vstack([mo.md("**Recently saved albums**"), mo.ui.table(_recent, selection=None)])
    return


@app.cell
def _(dataset):
    df_chart18 = dataset("""
        SELECT playlist_name, items_total,
               CASE WHEN is_mine THEN 'mine' WHEN is_collaborative THEN 'collaborative'
                    ELSE 'followed' END AS ownership
        FROM dim_playlist ORDER BY items_total DESC LIMIT 20
    """).df()
    return (df_chart18,)


@app.cell
def _(alt, df_chart18):
    _chart = (
        alt.Chart(df_chart18).mark_bar().encode(
            x=alt.X("items_total:Q", title="Tracks"),
            y=alt.Y("playlist_name:N", sort="-x", title=None),
            color=alt.Color("ownership:N", title=None),
            tooltip=["playlist_name:N", "ownership:N", "items_total:Q"]
        ).properties(title="My playlists and followed playlists, by size")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart4 = dataset("""
        SELECT DATE_TRUNC('month', added_at) AS month, COUNT(saved_track_sk) AS saved,
               SUM(COUNT(saved_track_sk)) OVER (ORDER BY DATE_TRUNC('month', added_at)) AS total_saved
        FROM fact_saved_track GROUP BY 1 ORDER BY 1
    """).df()
    return (df_chart4,)


@app.cell
def _(alt, df_chart4):
    _chart = (
        alt.Chart(df_chart4).mark_area(opacity=0.6).encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("total_saved:Q", title="Saved tracks (running total)"),
            tooltip=["month:T", "saved:Q", "total_saved:Q"]
        ).properties(title="Library growth")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart5 = dataset("""
        SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM fact_play p WHERE p.track_sk = s.track_sk AND p.played_at >= CURRENT_DATE - INTERVAL '30' DAY) AND NOT EXISTS (SELECT 1 FROM fact_top_item t WHERE t.track_sk = s.track_sk AND t.time_range = 'short_term' AND t.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item)) THEN 'forgotten' ELSE 'still in rotation' END AS status,
               COUNT(s.saved_track_sk) AS saved_tracks
        FROM fact_saved_track s GROUP BY 1
    """).df()
    return (df_chart5,)


@app.cell
def _(alt, df_chart5):
    _chart = (
        alt.Chart(df_chart5).mark_bar().encode(
            x=alt.X("saved_tracks:Q", title="Saved tracks"),
            y=alt.Y("status:N", title=None),
            color=alt.Color("status:N", legend=None),
            tooltip=["status:N", "saved_tracks:Q"]
        ).properties(title="Forgotten favorites vs tracks still in rotation")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart16 = dataset("""
        SELECT a.artist_name, COUNT(DISTINCT s.track_sk) AS liked_songs
        FROM fact_saved_track s
        JOIN bridge_track_artist b ON s.track_sk = b.track_sk
        JOIN dim_artist a ON b.artist_sk = a.artist_sk
        GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10
    """).df()
    return (df_chart16,)


@app.cell
def _(alt, df_chart16):
    _chart = (
        alt.Chart(df_chart16).mark_bar().encode(
            x=alt.X("liked_songs:Q", title="Liked songs"),
            y=alt.Y("artist_name:N", sort="-x", title=None),
            tooltip=["artist_name:N", "liked_songs:Q"]
        ).properties(title="Top 10 artists in my liked songs")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart15 = dataset("""
        SELECT pl.playlist_name, DATE_TRUNC('month', i.added_at) AS month,
               SUM(COUNT(i.playlist_item_sk)) OVER (PARTITION BY pl.playlist_name ORDER BY DATE_TRUNC('month', i.added_at)) AS total_tracks
        FROM fact_playlist_item i JOIN dim_playlist pl ON i.playlist_sk = pl.playlist_sk
        WHERE i.added_at IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2
    """).df()
    return (df_chart15,)


@app.cell
def _(alt, df_chart15):
    _chart = (
        alt.Chart(df_chart15).mark_line(point=True).encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("total_tracks:Q", title="Tracks (running total)"),
            color=alt.Color("playlist_name:N", title="Playlist"),
            tooltip=["playlist_name:N", "month:T", "total_tracks:Q"]
        ).properties(title="Playlist growth")
    )
    _chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## How my taste moves
    """)
    return


@app.cell
def _(dataset):
    df_chart6 = dataset("""
        SELECT a.artist_name,
               MAX(CASE WHEN t.time_range = 'long_term' THEN t.rank END) AS long_term_rank,
               MAX(CASE WHEN t.time_range = 'medium_term' THEN t.rank END) AS medium_term_rank,
               MAX(CASE WHEN t.time_range = 'short_term' THEN t.rank END) AS short_term_rank
        FROM fact_top_item t JOIN dim_artist a ON t.artist_sk = a.artist_sk
        WHERE t.item_type = 'artists' AND t.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item)
        GROUP BY 1
        HAVING MAX(CASE WHEN t.time_range = 'long_term' THEN t.rank END) <= 10
        ORDER BY long_term_rank
    """).df()
    return (df_chart6,)


@app.cell
def _(alt, df_chart6):
    _chart = (
        alt.Chart(df_chart6).transform_fold(
            ["long_term_rank", "medium_term_rank", "short_term_rank"], as_=["time_range", "rank"]
        ).mark_point(filled=True, size=90).encode(
            x=alt.X("rank:Q", scale=alt.Scale(reverse=True), title="Rank (1 = top)"),
            y=alt.Y("artist_name:N", sort=alt.EncodingSortField("long_term_rank"), title=None),
            color=alt.Color("time_range:N", title="Time range"),
            tooltip=["artist_name:N", "time_range:N", "rank:Q"]
        ).properties(title="Top 10 long-term artists: rank by time range")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart13 = dataset("""
        WITH latest AS (
          SELECT time_range, artist_sk FROM fact_top_item
          WHERE item_type = 'artists' AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item))
        SELECT x.time_range AS range_a, y.time_range AS range_b,
               COUNT(DISTINCT CASE WHEN x.artist_sk = y.artist_sk THEN x.artist_sk END) * 1.0
                 / COUNT(DISTINCT x.artist_sk) AS overlap
        FROM latest x CROSS JOIN latest y GROUP BY 1, 2 ORDER BY 1, 2
    """).df()
    return (df_chart13,)


@app.cell
def _(alt, df_chart13):
    _chart = (
        alt.Chart(df_chart13).mark_rect().encode(
            x=alt.X("range_b:N", sort=["short_term", "medium_term", "long_term"], title="Also in"),
            y=alt.Y("range_a:N", sort=["short_term", "medium_term", "long_term"], title="Top artists of"),
            color=alt.Color("overlap:Q", scale=alt.Scale(domain=[0, 1]), title="Overlap"),
            tooltip=["range_a:N", "range_b:N", alt.Tooltip("overlap:Q", format=".0%")]
        ).properties(title="Taste stability: top-artist overlap")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_chart14 = dataset("""
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
    """).df()
    return (df_chart14,)


@app.cell
def _(alt, df_chart14):
    _chart = (
        alt.Chart(df_chart14).mark_bar().encode(
            x=alt.X("rank:Q", scale=alt.Scale(reverse=True), title="Rank in its time range (1 = top)"),
            y=alt.Y("artist_name:N", sort=alt.EncodingSortField("rank"), title=None),
            color=alt.Color("movement:N", title=None),
            row=alt.Row("movement:N", title=None),
            tooltip=["movement:N", "artist_name:N", "rank:Q"]
        ).resolve_scale(y="independent").properties(title="New in my top (short_term) and faded (long_term)")
    )
    _chart
    return


if __name__ == "__main__":
    app.run()
