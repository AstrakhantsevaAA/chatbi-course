"""Build the listening_activity CDM from the raw Spotify tables.

Run `uv run python transformations/listening_activity_to_cdm.py` after
`spotify_pipeline.py`. The CDM loads through its own pipeline into its own
dataset, so re-running ingest never mixes raw and modelled tables.
"""

import os
from pathlib import Path

import dlt

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = os.getenv("SPOTIFY_DESTINATION", "playground")
UNKNOWN = "'UNKNOWN'"

TRACK_SOURCES = """
    SELECT track_id, track__name AS track_name, track__duration_ms AS duration_ms,
           track__explicit AS is_explicit, track__external_ids__isrc AS isrc,
           track__album__id AS album_id, track__external_urls__spotify AS spotify_url, 1 AS priority
    FROM saved_tracks
    UNION ALL
    SELECT track_id, track__name, track__duration_ms, track__explicit, track__external_ids__isrc,
           track__album__id, track__external_urls__spotify, 2
    FROM plays
    UNION ALL
    SELECT track_id, item__name, item__duration_ms, item__explicit, item__external_ids__isrc,
           item__album__id, item__external_urls__spotify, 3
    FROM playlist_items
    UNION ALL
    SELECT id, name, duration_ms, explicit, external_ids__isrc, album__id, external_urls__spotify, 4
    FROM top_items WHERE item_type = 'tracks'
"""

ALBUM_SOURCES = """
    SELECT track__album__id AS album_id, track__album__name AS album_name,
           track__album__album_type AS album_type, track__album__release_date AS release_date,
           track__album__release_date_precision AS release_date_precision,
           track__album__total_tracks AS total_tracks, 1 AS priority
    FROM saved_tracks
    UNION ALL
    SELECT track__album__id, track__album__name, track__album__album_type, track__album__release_date,
           track__album__release_date_precision, track__album__total_tracks, 2
    FROM plays
    UNION ALL
    SELECT item__album__id, item__album__name, item__album__album_type, item__album__release_date,
           item__album__release_date_precision, item__album__total_tracks, 3
    FROM playlist_items
    UNION ALL
    SELECT album__id, album__name, album__album_type, album__release_date,
           album__release_date_precision, album__total_tracks, 4
    FROM top_items WHERE item_type = 'tracks'
"""

TRACK_ARTISTS = """
    SELECT p.track_id, a.id AS artist_id, a.name AS artist_name,
           a.external_urls__spotify AS spotify_url, a._dlt_list_idx AS artist_position
    FROM plays__track__artists a JOIN plays p ON a._dlt_parent_id = p._dlt_id
    UNION ALL
    SELECT s.track_id, a.id, a.name, a.external_urls__spotify, a._dlt_list_idx
    FROM saved_tracks__track__artists a JOIN saved_tracks s ON a._dlt_parent_id = s._dlt_id
    UNION ALL
    SELECT i.track_id, a.id, a.name, a.external_urls__spotify, a._dlt_list_idx
    FROM playlist_items__item__artists a JOIN playlist_items i ON a._dlt_parent_id = i._dlt_id
    UNION ALL
    SELECT t.id, a.id, a.name, a.external_urls__spotify, a._dlt_list_idx
    FROM top_items__artists a JOIN top_items t ON a._dlt_parent_id = t._dlt_id
    WHERE t.item_type = 'tracks'
"""

KEY = {"data_type": "text", "nullable": False}
FK = {"data_type": "text", "nullable": False}


def first_by_priority(sources: str, key: str) -> str:
    """Wrap a UNION so each natural key keeps the row from the best source."""
    return f"""
        SELECT * FROM (
            SELECT u.*, ROW_NUMBER() OVER (PARTITION BY {key} ORDER BY priority) AS rn
            FROM ({sources}) u WHERE {key} IS NOT NULL
        ) ranked WHERE rn = 1
    """


@dlt.hub.transformation(
    write_disposition="replace",
    columns={"track_sk": KEY, "album_sk": FK, "source_pipeline": {"data_type": "text"}},
)
def dim_track(dataset: dlt.Dataset):
    yield dataset(f"""
        SELECT * FROM (
        SELECT MD5(track_id) AS track_sk, track_id AS source_id,
               'spotify_pipeline' AS source_pipeline, track_name, duration_ms, is_explicit, isrc,
               COALESCE(MD5(album_id), {UNKNOWN}) AS album_sk, spotify_url
        FROM ({first_by_priority(TRACK_SOURCES, "track_id")}) t
        UNION ALL
        SELECT {UNKNOWN}, {UNKNOWN}, 'spotify_pipeline', 'Unknown track (local file)',
               NULL, NULL, NULL, {UNKNOWN}, NULL
        ) u
    """)


@dlt.hub.transformation(
    write_disposition="replace",
    columns={"album_sk": KEY, "release_year": {"data_type": "bigint", "nullable": True}},
)
def dim_album(dataset: dlt.Dataset):
    yield dataset(f"""
        SELECT * FROM (
        SELECT MD5(album_id) AS album_sk, album_id AS source_id,
               'spotify_pipeline' AS source_pipeline, album_name, album_type, release_date,
               release_date_precision, CAST(SUBSTRING(release_date, 1, 4) AS BIGINT) AS release_year,
               total_tracks
        FROM ({first_by_priority(ALBUM_SOURCES, "album_id")}) a
        UNION ALL
        SELECT {UNKNOWN}, {UNKNOWN}, 'spotify_pipeline', 'Unknown album', NULL, NULL, NULL, NULL, NULL
        ) u
    """)


@dlt.hub.transformation(write_disposition="replace", columns={"artist_sk": KEY})
def dim_artist(dataset: dlt.Dataset):
    artists = f"""
        SELECT artist_id, artist_name, spotify_url, 1 AS priority FROM ({TRACK_ARTISTS}) ta
        UNION ALL
        SELECT id, name, external_urls__spotify, 0 FROM top_items WHERE item_type = 'artists'
    """
    yield dataset(f"""
        SELECT * FROM (
        SELECT MD5(artist_id) AS artist_sk, artist_id AS source_id,
               'spotify_pipeline' AS source_pipeline, artist_name, spotify_url
        FROM ({first_by_priority(artists, "artist_id")}) a
        UNION ALL
        SELECT {UNKNOWN}, {UNKNOWN}, 'spotify_pipeline', 'Unknown artist', NULL
        ) u
    """)


@dlt.hub.transformation(write_disposition="replace", columns={"playlist_sk": KEY})
def dim_playlist(dataset: dlt.Dataset):
    yield dataset("""
        SELECT MD5(id) AS playlist_sk, id AS source_id, 'spotify_pipeline' AS source_pipeline,
               name AS playlist_name, description, public AS is_public,
               collaborative AS is_collaborative, items__total AS items_total,
               owner__id AS owner_id, owner__display_name AS owner_display_name
        FROM playlists
    """)


@dlt.hub.transformation(
    write_disposition="replace",
    columns={"track_sk": FK, "artist_sk": FK, "artist_position": {"data_type": "bigint"}},
)
def bridge_track_artist(dataset: dlt.Dataset):
    yield dataset(f"""
        SELECT DISTINCT MD5(track_id) AS track_sk, MD5(artist_id) AS artist_sk,
               artist_position
        FROM ({TRACK_ARTISTS}) ta
        WHERE track_id IS NOT NULL AND artist_id IS NOT NULL
    """)


@dlt.hub.transformation(
    write_disposition="replace",
    columns={
        "play_sk": KEY, "track_sk": FK, "album_sk": FK,
        "played_date": {"data_type": "date"}, "context_type": {"data_type": "text"},
        "context_uri": {"data_type": "text", "nullable": True},
    },
)
def fact_play(dataset: dlt.Dataset):
    yield dataset(f"""
        SELECT MD5(CAST(played_at AS VARCHAR)) AS play_sk, played_at,
               CAST(played_at AS DATE) AS played_date,
               COALESCE(MD5(track_id), {UNKNOWN}) AS track_sk,
               COALESCE(MD5(track__album__id), {UNKNOWN}) AS album_sk,
               COALESCE(context__type, {UNKNOWN}) AS context_type,
               context__uri AS context_uri, track__duration_ms AS duration_ms
        FROM plays
    """)


@dlt.hub.transformation(
    write_disposition="replace",
    columns={"saved_track_sk": KEY, "track_sk": FK, "added_date": {"data_type": "date"}},
)
def fact_saved_track(dataset: dlt.Dataset):
    yield dataset("""
        SELECT MD5(track_id) AS saved_track_sk, MD5(track_id) AS track_sk, added_at,
               CAST(added_at AS DATE) AS added_date
        FROM saved_tracks WHERE track_id IS NOT NULL
    """)


@dlt.hub.transformation(
    write_disposition="replace",
    columns={
        "playlist_item_sk": KEY, "playlist_sk": FK, "track_sk": FK,
        "added_date": {"data_type": "date", "nullable": True},
    },
)
def fact_playlist_item(dataset: dlt.Dataset):
    yield dataset(f"""
        SELECT MD5(_playlists_id || '|' || COALESCE(track_id, _dlt_id) || '|'
                   || COALESCE(CAST(added_at AS VARCHAR), '')) AS playlist_item_sk,
               MD5(_playlists_id) AS playlist_sk,
               COALESCE(MD5(track_id), {UNKNOWN}) AS track_sk,
               added_at, CAST(added_at AS DATE) AS added_date, added_by__id AS added_by_id
        FROM playlist_items
    """)


@dlt.hub.transformation(
    write_disposition="replace",
    columns={
        "top_item_sk": KEY, "track_sk": FK, "artist_sk": FK,
        "snapshot_date": {"data_type": "date"}, "rank": {"data_type": "bigint"},
    },
)
def fact_top_item(dataset: dlt.Dataset):
    yield dataset(f"""
        SELECT MD5(snapshot_date || '|' || item_type || '|' || time_range || '|' || id) AS top_item_sk,
               CAST(snapshot_date AS DATE) AS snapshot_date, item_type, time_range, rank,
               CASE WHEN item_type = 'tracks' THEN MD5(id) ELSE {UNKNOWN} END AS track_sk,
               CASE WHEN item_type = 'artists' THEN MD5(id) ELSE {UNKNOWN} END AS artist_sk
        FROM top_items
    """)


@dlt.source
def listening_activity_to_cdm(dataset: dlt.Dataset):
    """Dimensions first, then the bridge, then facts."""
    yield dim_track(dataset)
    yield dim_album(dataset)
    yield dim_artist(dataset)
    yield dim_playlist(dataset)
    yield bridge_track_artist(dataset)
    yield fact_play(dataset)
    yield fact_saved_track(dataset)
    yield fact_playlist_item(dataset)
    yield fact_top_item(dataset)


def main() -> None:
    os.chdir(ROOT)
    # Pass destination and dataset: a platform run has no local pipeline state.
    source = dlt.attach("spotify_pipeline", destination=DESTINATION, dataset_name="spotify_raw")
    cdm = dlt.pipeline(
        # The pipeline name sets the DuckDB file; it must differ from the dataset name.
        pipeline_name="listening_activity_cdm",
        destination=DESTINATION,
        dataset_name="listening_activity",
    )
    print(cdm.run(listening_activity_to_cdm(source.dataset())))


if __name__ == "__main__":
    main()
