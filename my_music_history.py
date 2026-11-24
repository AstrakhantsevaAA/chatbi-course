"""My music history: a dltHub data app over years of library data, no plays.

Run `uv run marimo run my_music_history.py` after the CDM is built.
Recent plays come last, because they cover only the days since the first load.
Built with the AI Harness data-exploration toolkit from the history analysis plan.
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
def _():
    from destinations import cdm_dataset

    dataset = cdm_dataset()
    return (dataset,)


@app.cell
def _(dataset, mo):
    _k = dataset("""
        SELECT
          (SELECT COUNT(*) FROM fact_saved_track) AS liked_songs,
          (SELECT MIN(added_at) FROM fact_saved_track) AS liking_since,
          (SELECT COUNT(DISTINCT b.artist_sk) FROM bridge_track_artist b WHERE b.track_sk IN (SELECT track_sk FROM fact_saved_track UNION SELECT track_sk FROM fact_playlist_item)) AS artists,
          (SELECT COUNT(*) FROM fact_saved_album) AS saved_albums,
          (SELECT COUNT(*) FROM fact_playlist_item) AS playlist_additions,
          (SELECT MIN(a.release_year) FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk JOIN dim_album a ON t.album_sk = a.album_sk) AS oldest_release
    """).df().iloc[0]
    mo.vstack([
        mo.md("# My music history"),
        mo.hstack([
            mo.stat(value=f"{_k.liked_songs:,}", label=f"Liked songs since {_k.liking_since:%b %Y}"),
            mo.stat(value=f"{_k.artists:,}", label="Artists in my library"),
            mo.stat(value=f"{_k.saved_albums:,}", label="Saved albums"),
            mo.stat(value=f"{_k.playlist_additions:,}", label="Tracks added to playlists"),
            mo.stat(value=f"{int(_k.oldest_release)}", label="Oldest release I like"),
        ], justify="start"),
        mo.md("Built from my library and Spotify's own rankings, so it covers years, not days. "
              "My library = liked songs + tracks in playlists I own or collaborate on. "
              "Spotify does not return the tracks of playlists I only follow."),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## How my library grew
    """)
    return


@app.cell
def _(dataset):
    df_h1 = dataset("""
        SELECT DATE_TRUNC('month', added_at) AS month, COUNT(saved_track_sk) AS liked,
               SUM(COUNT(saved_track_sk)) OVER (ORDER BY DATE_TRUNC('month', added_at)) AS library_size
        FROM fact_saved_track GROUP BY 1 ORDER BY 1
    """).df()
    return (df_h1,)


@app.cell
def _(alt, df_h1):
    _chart = (
        alt.layer(
            alt.Chart(df_h1).mark_bar(opacity=0.5).encode(
                x=alt.X("month:T", title="Month"), y=alt.Y("liked:Q", title="Liked that month")),
            alt.Chart(df_h1).mark_line(color="#d62728").encode(
                x="month:T", y=alt.Y("library_size:Q", title="Library size")),
        ).resolve_scale(y="independent").encode(
            tooltip=["month:T", "liked:Q", "library_size:Q"]
        ).properties(title="Liked songs per month, and library size")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_h2 = dataset("""
        SELECT DATE_TRUNC('quarter', i.added_at) AS quarter, pl.playlist_name, COUNT(i.playlist_item_sk) AS added
        FROM fact_playlist_item i JOIN dim_playlist pl ON i.playlist_sk = pl.playlist_sk
        WHERE i.added_at IS NOT NULL GROUP BY 1, 2 ORDER BY 1
    """).df()
    return (df_h2,)


@app.cell
def _(alt, df_h2):
    _chart = (
        alt.Chart(df_h2).mark_bar().encode(
            x=alt.X("quarter:T", title="Quarter"),
            y=alt.Y("added:Q", title="Tracks added"),
            color=alt.Color("playlist_name:N", title="Playlist"),
            tooltip=["quarter:T", "playlist_name:N", "added:Q"]
        ).properties(title="Tracks added to playlists per quarter")
    )
    _chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## Who I love
    """)
    return


@app.cell
def _(dataset):
    df_h3 = dataset("""
        WITH library AS (
            SELECT track_sk, 'liked' AS source FROM fact_saved_track
            UNION
            SELECT i.track_sk, 'only in my playlists' FROM fact_playlist_item i
            WHERE i.track_sk <> 'UNKNOWN'
              AND i.track_sk NOT IN (SELECT track_sk FROM fact_saved_track)
        ),
        by_artist AS (
            SELECT a.artist_name, l.source, COUNT(DISTINCT l.track_sk) AS songs
            FROM library l
            JOIN bridge_track_artist b ON b.track_sk = l.track_sk
            JOIN dim_artist a ON a.artist_sk = b.artist_sk
            GROUP BY 1, 2
        ),
        top AS (
            SELECT artist_name, SUM(songs) AS total FROM by_artist
            GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 15
        )
        SELECT b.artist_name, b.source, b.songs, t.total
        FROM by_artist b JOIN top t ON b.artist_name = t.artist_name
        ORDER BY t.total DESC, b.artist_name
    """).df()
    return (df_h3,)


@app.cell
def _(alt, df_h3):
    _chart = (
        alt.Chart(df_h3).mark_bar().encode(
            x=alt.X("songs:Q", title="Songs in my library"),
            y=alt.Y("artist_name:N", sort=alt.EncodingSortField("total", order="descending"), title=None),
            color=alt.Color("source:N", title=None),
            tooltip=["artist_name:N", "source:N", "songs:Q", "total:Q"]
        ).properties(
            title="Top 15 artists in my library (liked songs and my playlists)"
        )
    )
    _chart
    return


@app.cell
def _(dataset):
    df_h4 = dataset("""
        WITH first_like AS (
          SELECT b.artist_sk, MIN(EXTRACT(YEAR FROM s.added_at)) AS first_year
          FROM fact_saved_track s JOIN bridge_track_artist b ON s.track_sk = b.track_sk GROUP BY 1)
        SELECT CAST(first_year AS VARCHAR) AS year, COUNT(*) AS new_artists FROM first_like GROUP BY 1 ORDER BY 1
    """).df()
    return (df_h4,)


@app.cell
def _(alt, df_h4):
    _chart = (
        alt.Chart(df_h4).mark_bar().encode(
            x=alt.X("year:O", title="Year of first liked song"),
            y=alt.Y("new_artists:Q", title="New artists"),
            tooltip=["year:O", "new_artists:Q"]
        ).properties(title="New artists in my library per year")
    )
    _chart
    return


@app.cell
def _(dataset, mo):
    _t = dataset("""
        WITH yearly AS (
          SELECT EXTRACT(YEAR FROM s.added_at) AS year, a.artist_name, COUNT(DISTINCT s.track_sk) AS liked_songs
          FROM fact_saved_track s JOIN bridge_track_artist b ON s.track_sk = b.track_sk JOIN dim_artist a ON b.artist_sk = a.artist_sk GROUP BY 1, 2),
        ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY year ORDER BY liked_songs DESC, artist_name) AS rn FROM yearly)
        SELECT CAST(year AS VARCHAR) AS year, artist_name, liked_songs, rn AS rank FROM ranked WHERE rn <= 3 ORDER BY year DESC, rn
    """).df()
    mo.vstack([mo.md("**Top 3 artists of each year (by songs liked that year)**"), mo.ui.table(_t, selection=None)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## What era I live in
    """)
    return


@app.cell
def _(dataset):
    df_h5 = dataset("""
        SELECT CAST(CAST(FLOOR(a.release_year / 10) * 10 AS INTEGER) AS VARCHAR) || 's' AS decade, COUNT(s.saved_track_sk) AS liked_songs
        FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk JOIN dim_album a ON t.album_sk = a.album_sk
        WHERE a.release_year IS NOT NULL GROUP BY 1 ORDER BY 1
    """).df()
    return (df_h5,)


@app.cell
def _(alt, df_h5):
    _chart = (
        alt.Chart(df_h5).mark_bar().encode(
            x=alt.X("decade:O", title="Release decade"),
            y=alt.Y("liked_songs:Q", title="Liked songs"),
            tooltip=["decade:O", "liked_songs:Q"]
        ).properties(title="Liked songs by release decade")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_h6 = dataset("""
        SELECT CAST(EXTRACT(YEAR FROM s.added_at) AS VARCHAR) AS year_liked,
               CAST(CAST(FLOOR(a.release_year / 10) * 10 AS INTEGER) AS VARCHAR) || 's' AS decade, COUNT(s.saved_track_sk) AS liked_songs
        FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk JOIN dim_album a ON t.album_sk = a.album_sk
        WHERE a.release_year IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2
    """).df()
    return (df_h6,)


@app.cell
def _(alt, df_h6):
    _chart = (
        alt.Chart(df_h6).mark_rect().encode(
            x=alt.X("year_liked:O", title="Year liked"),
            y=alt.Y("decade:O", sort="descending", title="Release decade"),
            color=alt.Color("liked_songs:Q", title="Liked songs"),
            tooltip=["year_liked:O", "decade:O", "liked_songs:Q"]
        ).properties(title="What I liked each year, by release decade")
    )
    _chart
    return


@app.cell
def _(mo):
    mo.md("""
    ## What Spotify sees
    """)
    return


@app.cell
def _(dataset):
    df_h7 = dataset("""
        WITH liked AS (
          SELECT b.artist_sk, COUNT(DISTINCT s.track_sk) AS liked_songs
          FROM fact_saved_track s JOIN bridge_track_artist b ON s.track_sk = b.track_sk GROUP BY 1)
        SELECT t.rank, a.artist_name, COALESCE(l.liked_songs, 0) AS liked_songs
        FROM fact_top_item t JOIN dim_artist a ON t.artist_sk = a.artist_sk
        LEFT JOIN liked l ON l.artist_sk = t.artist_sk
        WHERE t.item_type = 'artists' AND t.time_range = 'long_term'
          AND t.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item)
        ORDER BY t.rank LIMIT 15
    """).df()
    return (df_h7,)


@app.cell
def _(alt, df_h7):
    _chart = (
        alt.Chart(df_h7).mark_bar().encode(
            x=alt.X("liked_songs:Q", title="Liked songs by this artist"),
            y=alt.Y("artist_name:N", sort=alt.EncodingSortField("rank"), title="Spotify long-term top 15 (about 1 year)"),
            tooltip=["rank:Q", "artist_name:N", "liked_songs:Q"]
        ).properties(title="Spotify's long-term top artists, and how many of their songs I liked")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_h8 = dataset("""
        WITH latest AS (
          SELECT time_range, artist_sk FROM fact_top_item
          WHERE item_type = 'artists' AND snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item))
        SELECT x.time_range AS range_a, y.time_range AS range_b,
               COUNT(DISTINCT CASE WHEN x.artist_sk = y.artist_sk THEN x.artist_sk END) * 1.0
                 / COUNT(DISTINCT x.artist_sk) AS overlap
        FROM latest x CROSS JOIN latest y GROUP BY 1, 2 ORDER BY 1, 2
    """).df()
    return (df_h8,)


@app.cell
def _(alt, df_h8):
    _chart = (
        alt.Chart(df_h8).mark_rect().encode(
            x=alt.X("range_b:N", sort=["short_term", "medium_term", "long_term"], title="Also in"),
            y=alt.Y("range_a:N", sort=["short_term", "medium_term", "long_term"], title="Top artists of"),
            color=alt.Color("overlap:Q", scale=alt.Scale(domain=[0, 1]), title="Overlap"),
            tooltip=["range_a:N", "range_b:N", alt.Tooltip("overlap:Q", format=".0%")]
        ).properties(title="Top-artist overlap: 4 weeks, 6 months, 1 year")
    )
    _chart
    return


@app.cell
def _(dataset, mo):
    _t = dataset("""
        SELECT t.rank, d.track_name, ar.artist_name,
               CASE WHEN s.track_sk IS NOT NULL THEN 'liked' ELSE 'not liked' END AS in_library
        FROM fact_top_item t JOIN dim_track d ON t.track_sk = d.track_sk
        LEFT JOIN bridge_track_artist b ON b.track_sk = t.track_sk AND b.artist_position = 0
        LEFT JOIN dim_artist ar ON ar.artist_sk = b.artist_sk
        LEFT JOIN fact_saved_track s ON s.track_sk = t.track_sk
        WHERE t.item_type = 'tracks' AND t.time_range = 'long_term'
          AND t.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_top_item)
        ORDER BY t.rank LIMIT 10
    """).df()
    mo.vstack([mo.md("**Spotify's long-term top 10 tracks (about 1 year)**"), mo.ui.table(_t, selection=None)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## How my taste changed
    """)
    return


@app.cell
def _(dataset):
    df_h9 = dataset("""
        SELECT CAST(EXTRACT(YEAR FROM s.added_at) AS VARCHAR) AS year_liked,
               AVG(CASE WHEN t.is_explicit THEN 1.0 ELSE 0 END) AS explicit_share,
               AVG(t.duration_ms) / 60000.0 AS avg_minutes,
               AVG(CASE WHEN a.album_type = 'single' THEN 1.0 ELSE 0 END) AS singles_share
        FROM fact_saved_track s JOIN dim_track t ON s.track_sk = t.track_sk JOIN dim_album a ON t.album_sk = a.album_sk
        GROUP BY 1 ORDER BY 1
    """).df()
    return (df_h9,)


@app.cell
def _(alt, df_h9):
    _chart = (
        alt.Chart(df_h9).transform_fold(
            ["explicit_share", "singles_share"], as_=["measure", "share"]
        ).mark_line(point=True).encode(
            x=alt.X("year_liked:O", title="Year liked"),
            y=alt.Y("share:Q", axis=alt.Axis(format="%"), title="Share of liked songs"),
            color=alt.Color("measure:N", title=None),
            tooltip=["year_liked:O", "measure:N", alt.Tooltip("share:Q", format=".0%")]
        ).properties(title="Explicit songs and singles among what I liked each year")
    )
    _chart
    return


@app.cell
def _(dataset, mo):
    _r = dataset("""
        SELECT COUNT(play_sk) AS plays, SUM(duration_ms) / 60000.0 AS listening_minutes,
               MIN(played_at) AS data_from, MAX(played_at) AS data_through
        FROM fact_play
    """).df().iloc[0]
    mo.vstack([
        mo.md("## Recent listening"),
        mo.md(f"Plays from **{_r.data_from:%Y-%m-%d}** to **{_r.data_through:%Y-%m-%d}** only: "
              "Spotify keeps the last 50 plays, and the history grows with every scheduled load. "
              "Hours are in UTC."),
        mo.hstack([
            mo.stat(value=f"{_r.plays:,}", label="Plays"),
            mo.stat(value=f"{_r.listening_minutes:,.0f}", label="Listening minutes"),
        ], justify="start"),
    ])
    return


@app.cell
def _(dataset):
    df_r1 = dataset("""
        SELECT a.artist_name, COUNT(p.play_sk) AS plays
        FROM fact_play p
        JOIN bridge_track_artist b ON p.track_sk = b.track_sk
        JOIN dim_artist a ON b.artist_sk = a.artist_sk
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """).df()
    return (df_r1,)


@app.cell
def _(alt, df_r1):
    _chart = (
        alt.Chart(df_r1).mark_bar().encode(
            x=alt.X("plays:Q", title="Plays"),
            y=alt.Y("artist_name:N", sort="-x", title=None),
            tooltip=["artist_name:N", "plays:Q"]
        ).properties(title="Top 10 artists by plays")
    )
    _chart
    return


@app.cell
def _(dataset):
    df_r2 = dataset("""
        SELECT ISODOW(played_at) AS weekday_no, DAYNAME(played_at) AS weekday,
               EXTRACT(HOUR FROM played_at) AS hour_utc, COUNT(play_sk) AS plays
        FROM fact_play GROUP BY 1, 2, 3 ORDER BY 1, 3
    """).df()
    return (df_r2,)


@app.cell
def _(alt, df_r2):
    _chart = (
        alt.Chart(df_r2).mark_rect().encode(
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
    df_r3 = dataset("""
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
    return (df_r3,)


@app.cell
def _(alt, df_r3):
    _chart = (
        alt.Chart(df_r3).mark_bar().encode(
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
    import chatbi

    _turns = []

    def _ask(messages, config):
        """Answer the newest chat message with the plan, gate, answer loop."""
        try:
            turn = chatbi.ask(messages[-1].content, _turns)
        except Exception as error:  # noqa: BLE001
            return f"Sorry, I could not answer: {error}"
        _turns.append(turn)
        parts = [mo.md(turn.answer)]
        if turn.rows is not None and len(turn.rows):
            parts.append(mo.ui.table(turn.rows.head(chatbi.MAX_ROWS_SHOWN), selection=None))
        if turn.sql:
            parts.append(mo.accordion({"SQL (passed the gate)": mo.md(f"```sql\n{turn.sql}\n```")}))
        return mo.vstack(parts)

    chat = mo.ui.chat(
        _ask,
        prompts=[
            "How many songs by my top artist do I have in my library?",
            "Which artist has the most songs in my library?",
            "How many albums have I saved, and by whom?",
            "Which artists did I play most this week?",
        ],
    )
    mo.vstack([
        mo.md("## Ask my music data"),
        mo.md("Questions run through the same plan → gate → read-only SQL loop as the "
              "answering agent. Every answer shows the SQL that ran."),
        chat,
    ])
    return


if __name__ == "__main__":
    app.run()
