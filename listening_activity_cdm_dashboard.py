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
    pipeline = dlt.attach("listening_activity_cdm")
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
              "It grows with every scheduled load."),
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
    ## My library
    """)
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
def _(mo):
    mo.md("""
    ## How my taste changes
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


if __name__ == "__main__":
    app.run()
